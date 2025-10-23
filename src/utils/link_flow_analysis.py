# Standard library imports
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

# Third-party imports
import numpy as np
import pandas as pd


def parse_link_flow_xml_to_pandas(
    base_dir: Path,
    sim_link_file: Path,
    prefix_output: str,
    sensor_start_time: float,
    sensor_end_time: float,
    link_list: Optional[list[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Path]:
    """
    Parse a SUMO edgeData XML file and return aggregated link-level statistics as pandas DataFrames.

    Parameters
    ----------
    base_dir : Path
        Base directory where outputs will be saved.
    sim_link_file : Path
        Path to the SUMO edgeData.xml output file.
    prefix_output : str
        Prefix for the saved CSV file.
    sensor_start_time : float
        Sensor data collection start time (seconds).
    sensor_end_time : float
        Sensor data collection end time (seconds).
    link_list : Optional[list[str]]
        List of links to filter (if specified).

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame, Path]
        - Aggregated link-level DataFrame
        - Raw interval-level DataFrame
        - Path to the saved CSV file
    """
    output_file = Path(base_dir) / f"{prefix_output}_link_measurements.csv"

    root = ET.parse(sim_link_file).getroot()
    data = []

    for interval in root.findall("interval"):
        interval_id = interval.get("id")

        interval_begin_str = interval.get("begin")
        interval_end_str = interval.get("end")
        interval_begin = float(interval_begin_str) if interval_begin_str is not None else 0.0
        interval_end = float(interval_end_str) if interval_end_str is not None else 0.0

        for link in interval.findall("edge"):
            link_id = link.get("id")
            speed_str = link.get("speed")
            arrived_str = link.get("arrived")
            left_str = link.get("left")

            link_data = {
                "interval_begin": interval_begin,
                "interval_end": interval_end,
                "interval_id": interval_id,
                "link_id": link_id,
                "link_speed": float(speed_str)*2.23694 if speed_str is not None else 0.0,
                "link_arrived": float(arrived_str) if arrived_str is not None else 0.0,
                "link_left": float(left_str) if left_str is not None else 0.0,
            }
            data.append(link_data)

    df_trips = pd.DataFrame(data)[
        [
            "interval_begin",
            "interval_end",
            "link_id",
            "link_speed",
            "link_arrived",
            "link_left",
        ]
    ]

    df_trips.to_csv(output_file, index=False)

    df_trips["interval_nVehContrib"] = df_trips["link_arrived"] + df_trips["link_left"]

    df_trips["interval_harmonicMeanSpeed"] = df_trips.loc[df_trips["interval_nVehContrib"] > 0, "link_speed"]

    df_trips = df_trips[
        (df_trips["interval_begin"] >= sensor_start_time) & (df_trips["interval_end"] <= sensor_end_time)
    ]

    df_agg = df_trips.groupby("link_id", as_index=False).agg(
        {"interval_nVehContrib": "sum", "interval_harmonicMeanSpeed": "mean"}
    )

    if link_list is not None:
        print(f"Filtering links to: {link_list}")
        df_agg = df_agg[df_agg["link_id"].isin(link_list)]

    return df_agg, df_trips, output_file


def compute_nrmse_all_links(eval_measure: str, df_true: pd.DataFrame, df_simulated: pd.DataFrame) -> float:
    """
    Compute NRMSE (Normalized Root Mean Squared Error) between simulated and ground truth link flows.

    Parameters
    ----------
    eval_measure : str
        Type of evaluation measurement (e.g., 'count', 'speed').
    df_true : pd.DataFrame
        DataFrame containing ground truth link measurements with column 'interval_nVehContrib'
        or 'interval_harmonicMeanSpeed' depending on eval_measure.
    df_simulated : pd.DataFrame
        DataFrame containing simulated link measurements with column 'interval_nVehContrib'
        or 'interval_harmonicMeanSpeed' depending on eval_measure.

    Returns
    -------
    float
        NRMSE value across all links.
    """
    # Convert link_id columns to string
    df_true["link_id"] = df_true["link_id"].astype(str)
    df_simulated["link_id"] = df_simulated["link_id"].astype(str)
    df_merged = df_true.merge(df_simulated, on="link_id", suffixes=("_GT", "_sim"), how="left")
    n = df_merged.shape[0]

    # Fill missing simulated values with 0 & compute squared differences
    if eval_measure == 'count':
        df_merged["interval_nVehContrib_sim"] = df_merged["interval_nVehContrib_sim"].fillna(0)
        df_merged["diff_square"] = (df_merged["interval_nVehContrib_GT"] - df_merged["interval_nVehContrib_sim"]) ** 2
        nrmse: float = np.sqrt(n * df_merged["diff_square"].sum()) / df_merged["interval_nVehContrib_GT"].sum()
    elif eval_measure == 'speed':
        df_merged["interval_harmonicMeanSpeed_sim"] = df_merged["interval_harmonicMeanSpeed_sim"].fillna(0)
        df_merged["diff_square"] = (df_merged["interval_harmonicMeanSpeed_GT"] - df_merged["interval_harmonicMeanSpeed_sim"]) ** 2
        nrmse: float = np.sqrt(n * df_merged["diff_square"].sum()) / df_merged["interval_harmonicMeanSpeed_GT"].sum()
    else:
        raise ValueError(f"Unsupported eval_measure: {eval_measure}")

    return nrmse
