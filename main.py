import argparse
import logging
import pandas as pd
import numpy as np
from faker import Faker
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.
    """
    parser = argparse.ArgumentParser(description="Creates a statistically representative subset of a larger dataset.")
    parser.add_argument("input_file", help="Path to the input CSV file.")
    parser.add_argument("output_file", help="Path to the output CSV file for the subset.")
    parser.add_argument("--subset_size", type=int, required=True, help="Number of rows to include in the subset.")
    parser.add_argument("--stratify_by", nargs='+', help="List of column names to use for stratified sampling.", required=True)
    parser.add_argument("--random_state", type=int, default=42, help="Random state for reproducibility.")
    parser.add_argument("--mask_columns", nargs='+', help="List of column names to mask with fake data.", default=[])
    return parser

def create_subset(input_file, output_file, subset_size, stratify_by, random_state, mask_columns):
    """
    Creates a stratified subset of the input data.

    Args:
        input_file (str): Path to the input CSV file.
        output_file (str): Path to the output CSV file.
        subset_size (int): Number of rows to include in the subset.
        stratify_by (list): List of column names to use for stratification.
        random_state (int): Random state for reproducibility.
        mask_columns (list): List of column names to mask with fake data.
    """
    try:
        # Input validation
        if os.path.exists(input_file) and os.path.realpath(input_file) == os.path.realpath(output_file):
            raise ValueError("Output file must not be the same as the input file.")
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
        if not input_file.lower().endswith('.csv'):
            raise ValueError("Input file must be a CSV file.")
        if subset_size <= 0:
            raise ValueError("Subset size must be a positive integer.")

        logging.info(f"Reading data from {input_file}...")
        df = pd.read_csv(input_file)

        # Check if stratify_by columns exist
        for col in stratify_by:
            if col not in df.columns:
                raise ValueError(f"Stratify column '{col}' not found in the input file.")
        
        # Check if mask_columns exist
        for col in mask_columns:
            if col not in df.columns:
                raise ValueError(f"Mask column '{col}' not found in the input file.")

        logging.info("Creating stratified subset...")
        if subset_size > len(df):
            logging.warning(f"Subset size {subset_size} exceeds row count {len(df)}; returning all rows.")

        # Iterate the groups instead of groupby.apply: on pandas 2.2 the
        # apply path drops the grouping columns from the result, so the
        # subset silently lost the very columns it was stratified by.
        # Each stratum contributes its proportional share, at least one row
        # while rows remain, so a small stratum is not rounded away to zero.
        parts = []
        for _, group in df.groupby(stratify_by, sort=False):
            share = int(subset_size * len(group) / len(df))
            take = min(len(group), max(1, share)) if subset_size >= 1 else 0
            parts.append(group.sample(take, random_state=random_state))
        subset = pd.concat(parts) if parts else df.iloc[0:0]

        # Proportional rounding can land below the requested size; top up
        # from the rows no stratum claimed so the output size is exact
        # (capped by the input size, as the over-request warning states).
        if len(subset) < min(subset_size, len(df)):
            remaining = df.drop(index=subset.index)
            need = min(subset_size, len(df)) - len(subset)
            subset = pd.concat([subset, remaining.sample(need, random_state=random_state)])

        if len(subset) > subset_size:
          subset = subset.sample(subset_size, random_state=random_state)

        logging.info("Masking data...")
        # Masking draws from Faker and numpy, neither of which the sampling
        # random_state touches. Seed both, or two runs with the same
        # --random_state sample the same rows but mask them differently.
        fake = Faker()
        fake.seed_instance(random_state)
        np.random.seed(random_state)
        for col in mask_columns:
            if df[col].dtype == 'object':  # Mask string columns with fake names
                subset[col] = [fake.name() for _ in range(len(subset))]
            elif pd.api.types.is_numeric_dtype(df[col]):  # Mask numeric columns with random numbers
                # randint excludes the high end; add 1 so the column maximum
                # is reachable, and guard the constant-column case (min equal
                # to max would make randint raise low >= high).
                low, high = int(df[col].min()), int(df[col].max())
                subset[col] = np.random.randint(low, high + 1, len(subset)) if high > low else low
            else:
                logging.warning(f"Column {col} has unsupported data type for masking.")

        logging.info(f"Writing subset to {output_file}...")
        subset.to_csv(output_file, index=False)

        logging.info("Subset creation and masking complete.")

    except FileNotFoundError as e:
        logging.error(f"File not found error: {e}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Value error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        logging.exception(e)
        sys.exit(1)


def main():
    """
    Main function to parse arguments and call the subset creation function.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    create_subset(args.input_file, args.output_file, args.subset_size, args.stratify_by, args.random_state, args.mask_columns)

if __name__ == "__main__":
    # Example usage:
    # 1. Create a dummy CSV file:
    #    import pandas as pd
    #    data = {'Category': ['A', 'A', 'B', 'B', 'C', 'C', 'A', 'B'],
    #            'Value': [10, 12, 15, 11, 18, 20, 13, 16],
    #            'Name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Fred', 'Grace', 'Henry']}
    #    df = pd.DataFrame(data)
    #    df.to_csv('dummy_data.csv', index=False)
    #
    # 2. Run the script:
    #    python main.py dummy_data.csv output.csv --subset_size 4 --stratify_by Category --mask_columns Name
    main()