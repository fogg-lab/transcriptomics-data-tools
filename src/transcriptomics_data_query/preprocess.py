from typing import Union, Iterable
import subprocess
import shutil
import os.path

import pkg_resources
import requests
import pandas as pd
import mygene


CORE_MATRISOME_URL = "https://www.gsea-msigdb.org/gsea/msigdb/human/download_geneset.jsp?geneSetName=NABA_CORE_MATRISOME&fileType=json"
ALL_MATRISOME_URL = "https://www.gsea-msigdb.org/gsea/msigdb/human/download_geneset.jsp?geneSetName=NABA_MATRISOME&fileType=json"


def normalize_microarray(input_dir, output_file, remove_cel_dir=False):
    """Normalize microarray expression data given a directory containing CEL.gz files.

    Args:
        input_dir (str): Path to the directory containing CEL.gz files.
        output_file (str): Path to the output file.
        remove_cel_dir (bool, optional): If True, remove the input directory after normalization. Defaults to False.
    """
    r_script_path = pkg_resources.resource_filename('transcriptomics_data_query',
                                                    'rscripts/rma_normalization.R')
    print(f"Executing: Rscript {r_script_path} {input_dir} {output_file}")
    subprocess.run(["Rscript", r_script_path, input_dir, output_file], check=True)
    print("Normalization complete.")
    if remove_cel_dir:
        shutil.rmtree(input_dir)


def normalize_rnaseq(expression_file, clinical_file, output_file):
    """Normalize RNA-seq expression data given a file containing raw counts.

    Args:
        expression_file (str): Path to the input file containing raw counts.
        clinical_file (str): Path to the input file containing clinical data.
        output_file (str): Path to the output file.
    """
    r_script_path = pkg_resources.resource_filename('transcriptomics_data_query',
                                                    'rscripts/rnaseq_normalization.R')

    command = ["Rscript", r_script_path, expression_file, clinical_file, output_file]

    print(f"Executing: {' '.join(command)}")
    subprocess.run(command, check=True)
    print("Normalization complete.")


def normalize(input_path, output_file, clinical_file=None):
    """Normalize microarray or RNASeq expression data.

    Args:
        input_path (str): Path to the input file (for RNASeq) or directory (for microarray).
        output_file (str): Path to the output file.
        clinical_file (str, optional): Path to the input file containing clinical data.
            Not required for microarray.
        norm_method (str, optional): Normalization method employed if data is RNASeq (tmm or rle).
            Defaults to "tmm". For microarray, RMA normalization is used.
    """
    if os.path.isdir(input_path):
        normalize_microarray(input_path, output_file, remove_cel_dir=True)
    else:
        normalize_rnaseq(input_path, clinical_file, output_file)


def get_genes_from_file(filename):
    """Read genes from a text file with one gene symbol per line.

    Args:
        filename (str): Path to the text file containing gene symbols.

    Returns:
        list: List of gene symbols.
    """
    with open(filename, 'r', encoding='utf-8') as file:
        genes = [line.strip() for line in file]

    return genes


def get_matrisome_genes(core_matrisome_only=False):
    """Retrieve the human matrisome genes from MSigDB.

    Args:
        core_matrisome_only (bool, optional): If True, only retrieve the core matrisome genes.
            Defaults to False.

    Returns:
        list: List of matrisome gene symbols.
    """
    if core_matrisome_only:
        url = CORE_MATRISOME_URL
        field = "NABA_CORE_MATRISOME"
    else:
        url = ALL_MATRISOME_URL
        field = "NABA_MATRISOME"

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    matrisome_genes = response.json()[field]["geneSymbols"]
    return matrisome_genes


def convert_genes(genes: Iterable, in_format: str, out_format: str, species: str="human",
                  returnall: bool=False) -> pd.Series:
    """Converts a list of genes between formats 'entrezgene', 'ensembl.gene', and 'symbol'.

    Args:
        genes (Union[List, pd.Series]): A list of genes.
        in_format (str): The format of the input genes.
        out_format (str): The format of the output genes.
        species (str, optional): The species of the genes. Defaults to "human".
        returnall (bool, optional): Whether to return return complete lists of duplicate
            or missing query terms. Defaults to False.

    Returns:
        pd.Series: Query results. Index is the input genes, values are the output genes.
    """
    # Validate in_format and out_format
    valid_formats = ["entrezgene", "ensembl.gene", "symbol"]
    given_invalid = [f for f in [in_format, out_format] if f not in valid_formats]
    if len(given_invalid) > 0:
        raise ValueError(f"Invalid format(s) given: {given_invalid}. Valid formats: {valid_formats}")
    elif in_format == out_format:
        print("Input and output formats are the same. Returning input genes.")
        return pd.Series(genes, index=genes)

    mg = mygene.MyGeneInfo()
    out = mg.querymany(genes, scopes=in_format, fields=out_format, species=species,
                       as_dataframe=True, returnall=returnall)

    return out[out_format]


def select_rows(df, values, column=None):
    """Select rows in DataFrame.

    Args:
        df (pandas.DataFrame): The data frame.
        values (list): The values to select (e.g., ["A2M","A2ML1","ABI3BP"]).
        column (str, optional): The column name (e.g., "gene_symbol"). If None, the index is used.

    Returns:
        pandas.DataFrame: The selected rows.

    Example:
        >>> import transcriptomics_data_query as tdq
        >>> expression_df = pd.DataFrame({"GSM1234": [3.452, 4.123, 5.678, 6.789],
                                          "GSM5678": [1.234, 2.345, 3.456, 4.567]})
        >>> expression_df.index = ["A1BG", "A2M", "CA10", "SEMA6B"]
        >>> expression_df.index.name = "symbol"
        >>> matrisome_genes = tdq.preprocess.get_matrisome_genes()
        >>> matrisome_expression_df = tdq.preprocess.select_rows(expression_df, matrisome_genes)
        >>> matrisome_expression_df
                GSM1234 GSM5678
        symbol
           A2M    4.123   2.345
        SEMA6B    6.789   4.567
    """
    if column is None:
        return df.loc[df.index.isin(values)]

    return df[df[column].isin(values)]


def drop_nan_row_indices(expr_df: pd.DataFrame):
    """Drop rows where the row index is NaN.

    Args:
        expr_df (pandas.DataFrame): The expression matrix.

    Returns:
        pandas.DataFrame: The expression matrix with NaN rows dropped.
    """
    return expr_df.loc[expr_df.index.dropna()]
