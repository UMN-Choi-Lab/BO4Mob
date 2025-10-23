# Standard library imports
import json
import multiprocessing as mp
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

# Third-party imports
import pandas as pd


def load_config_full_opt(base_path: str, model_name: str, kernel: str, config_file_name: str) -> dict:
    """Load and format full optimization simulation configuration into a flat dictionary."""
    config_path = Path(base_path, "config")
    sim_setup = json.load(open(config_path / config_file_name))

    kwargs_config = {}

    # Basic identifiers
    kwargs_config["network_name"] = sim_setup["network_name"]
    kwargs_config["model_name"] = model_name
    kwargs_config["kernel"] = kernel

    # Paths to SUMO network-related files
    kwargs_config["network_path"] = Path("network", sim_setup["network_name"])
    kwargs_config["taz_xml"] = Path(base_path, kwargs_config["network_path"], "taz.xml")
    kwargs_config["net_xml"] = Path(base_path, kwargs_config["network_path"], "net.xml")
    kwargs_config["routes_csv"] = Path(base_path, kwargs_config["network_path"], "routes.csv")
    kwargs_config["od_xml"] = Path(base_path, kwargs_config["network_path"], "od.xml")
    kwargs_config["additional_xml"] = Path(base_path, kwargs_config["network_path"], "additional.xml")
    kwargs_config["link_selection_txt"] = Path(base_path, kwargs_config["network_path"], "link_selection.txt")

    # Output directory
    if model_name == "initSearch":
        kwargs_config["path_opt"] = f"output/full_optimization/{kwargs_config['network_name']}_initSearch_"
    else:
        kwargs_config["path_opt"] = (
            f"output/full_optimization/{kwargs_config['network_name']}_{kwargs_config['model_name']}_{kwargs_config['kernel']}_"
        )
    kwargs_config["path_init"] = f"output/full_optimization/{kwargs_config['network_name']}_initSearch_"

    # Simulation output file names
    kwargs_config["link_data_out_str"] = "edge_data.xml"
    kwargs_config["trips_xml_out_str"] = "trips.xml"

    # Environment settings
    kwargs_config["sumo_path"] = os.environ["SUMO_HOME"]

    # Simulation time settings
    kwargs_config["sim_start_time"] = sim_setup["sim_start_time"]
    kwargs_config["sim_end_time"] = sim_setup["sim_end_time"]
    kwargs_config["sim_stat_freq_sec"] = sim_setup["sim_stat_freq_sec"]

    # Sensor settings
    kwargs_config["sensor_start_time"] = sim_setup["sensor_start_time"]
    kwargs_config["sensor_end_time"] = sim_setup["sensor_end_time"]

    # OD (Origin-Destination) settings
    kwargs_config["od_end_time"] = sim_setup["od_end_time"]
    kwargs_config["od_bound_start"] = sim_setup["od_bound_start"]
    kwargs_config["od_bound_end"] = sim_setup["od_bound_end"]
    kwargs_config["n_init_search"] = sim_setup["n_init_search"]

    # Optimization parameters
    kwargs_config["n_epoch"] = sim_setup["n_epoch"]
    kwargs_config["bo_batch_size"] = sim_setup["bo_batch_size"]
    kwargs_config["bo_num_restarts"] = sim_setup["bo_num_restarts"]
    kwargs_config["bo_raw_samples"] = sim_setup["bo_raw_samples"]
    kwargs_config["bo_sample_shape"] = sim_setup["bo_sample_shape"]

    # System
    kwargs_config["cpu_counts"] = mp.cpu_count()

    # Cleanup flag
    kwargs_config["eliminate_sumo_run_files"] = sim_setup["eliminate_sumo_run_files"]

    return kwargs_config


def load_config_single_od_run(base_path: str, config_file_name: str) -> dict:
    """Load and format single OD run simulation configuration into a flat dictionary."""
    config_path = Path(base_path, "config")
    sim_setup = json.load(open(config_path / config_file_name))

    kwargs_config = {}

    # Basic identifiers
    kwargs_config["network_name"] = sim_setup["network_name"]

    # Paths to SUMO network-related files
    kwargs_config["network_path"] = Path("network", sim_setup["network_name"])
    kwargs_config["taz_xml"] = Path(base_path, kwargs_config["network_path"], "taz.xml")
    kwargs_config["net_xml"] = Path(base_path, kwargs_config["network_path"], "net.xml")
    kwargs_config["routes_csv"] = Path(base_path, kwargs_config["network_path"], "routes.csv")
    kwargs_config["od_xml"] = Path(base_path, kwargs_config["network_path"], "od.xml")
    kwargs_config["additional_xml"] = Path(base_path, kwargs_config["network_path"], "additional.xml")
    kwargs_config["link_selection_txt"] = Path(base_path, kwargs_config["network_path"], "link_selection.txt")

    # Output directory
    kwargs_config["path_run"] = f"output/single_od_run/{kwargs_config['network_name']}_"

    # Simulation output file names
    kwargs_config["link_data_out_str"] = "edge_data.xml"
    kwargs_config["trips_xml_out_str"] = "trips.xml"

    # Environment settings
    kwargs_config["sumo_path"] = os.environ["SUMO_HOME"]

    # Simulation time settings
    kwargs_config["sim_start_time"] = sim_setup["sim_start_time"]
    kwargs_config["sim_end_time"] = sim_setup["sim_end_time"]
    kwargs_config["sim_stat_freq_sec"] = sim_setup["sim_stat_freq_sec"]

    # Sensor settings
    kwargs_config["sensor_start_time"] = sim_setup["sensor_start_time"]
    kwargs_config["sensor_end_time"] = sim_setup["sensor_end_time"]

    # OD (Origin-Destination) settings
    kwargs_config["od_end_time"] = sim_setup["od_end_time"]
    kwargs_config["od_bound_start"] = sim_setup["od_bound_start"]
    kwargs_config["od_bound_end"] = sim_setup["od_bound_end"]

    # Cleanup flag
    kwargs_config["eliminate_sumo_run_files"] = sim_setup["eliminate_sumo_run_files"]

    return kwargs_config


def od_xml_to_df(file_path: Path) -> pd.DataFrame:
    """Parse an OD XML file and return it as a pandas DataFrame."""
    tree = ET.parse(file_path)
    root = tree.getroot()
    gt_od_df = xml2df_str(root, "tazRelation")
    return gt_od_df


def xml2df_str(root: ET.Element, row_str: str) -> pd.DataFrame:
    """Convert matching XML elements under a root into a pandas DataFrame."""
    return pd.DataFrame(list(iter_str(root, row_str)))


def iter_str(author: ET.Element, row_str: str):
    """Generate dictionaries from XML elements matching a specific tag."""
    author_attr = author.attrib
    for doc in author.iter(row_str):
        doc_dict = author_attr.copy()
        doc_dict.update(doc.attrib)
        doc_dict["data"] = doc.text or ""
        yield doc_dict


def iter_str_in_chunks(file: Union[str, Path], row_str: str):
    """Iterate over XML file and yield parsed elements one by one."""
    file = str(file)  # ensure it's a string path
    context = ET.iterparse(file, events=("start", "end"))
    _, root = next(context)

    for event, elem in context:
        if event == "end" and elem.tag == row_str:
            doc_dict = elem.attrib.copy()
            doc_dict["data"] = elem.text
            yield doc_dict
            elem.clear()


def xml2df_str_in_chunks(file: Union[str, Path], row_str: str, chunk_size: int = 1000):
    """Convert large XML file to DataFrames in chunks."""
    chunk = []
    for record in iter_str_in_chunks(file, row_str):
        chunk.append(record)
        if len(chunk) >= chunk_size:
            yield pd.DataFrame(chunk)
            chunk = []
    if chunk:
        yield pd.DataFrame(chunk)
