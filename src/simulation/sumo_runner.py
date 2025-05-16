# Standard library imports
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

# Third-party imports
import numpy as np
import pandas as pd

# Local application imports
from simulation.data_loader import xml2df_str_in_chunks


def simulate_od(
    od_xml: Path,
    prefix_output: str,
    base_dir: Path,
    net_xml: Path,
    taz_xml: Path,
    additional_xml: Path,
    routes_df: pd.DataFrame,
    routes_per_od: str,
    sim_end_time: int,
    trips_xml_out_str: str,
    sim_start_time: int = 0,
    seed: int = 0,
    timeout: int = 300,
) -> None:
    """
    Run a full SUMO simulation: generate trips from OD matrix, fix routes, and simulate.

    Parameters
    ----------
    od_xml : Path
        Path to the OD XML file.
    prefix_output : str
        Prefix to use for all output files.
    base_dir : Path
        Base directory where network and simulation files are located.
    net_xml : Path
        Path to the SUMO network file.
    taz_xml : Path
        Path to the TAZ (Traffic Assignment Zones) file.
    additional_xml : Path
        Path to additional SUMO files.
    routes_df : pd.DataFrame
        DataFrame containing the subset of routes to be used.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    sim_end_time : int
        Simulation end time in seconds.
    trips_xml_out_str : str
        Name for the output trips file.
    sim_start_time : int, optional
        Simulation start time in seconds. Defaults to 0.
    seed : int, optional
        Random seed for SUMO simulation. Defaults to 0.
    timeout : int, optional
        Timeout for waiting on trip file creation (seconds). Defaults to 300.
    """
    base_dir = Path(base_dir)

    # Prepare paths
    trip_output_before = base_dir / f"{prefix_output}_{trips_xml_out_str[:-4]}_beforeRteUpdates.xml"
    trip_output_after = base_dir / f"{prefix_output}_{trips_xml_out_str}"

    # Step 1: Generate trips using od2trips
    od2trips_cmd = [
        "od2trips",
        "--spread.uniform",
        "--taz-files",
        str(taz_xml),
        "--tazrelation-files",
        str(od_xml),
        "-o",
        str(trip_output_before),
    ]

    print(f"Running od2trips:\n{' '.join(od2trips_cmd)}")
    try:
        subprocess.run(od2trips_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to generate trips with od2trips: {e}")

    # Step 2: Wait for trips file to be created
    print(f"Waiting for trip file to be generated: {trip_output_before}")
    start_time = time.time()
    while not trip_output_before.exists():
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Timeout: Trip file not created within {timeout} seconds: {trip_output_before}")
        time.sleep(0.5)
    print(f"Trip file ready after {time.time() - start_time:.2f} seconds.")

    # Step 3: Fix trips with predefined route information
    update_trip_routes(trip_output_before, trip_output_after, routes_df, routes_per_od)

    # Step 4: Run SUMO simulation
    sumo_cmd = [
        "sumo",
        "--output-prefix",
        f"{prefix_output}_",
        "--ignore-route-errors",
        "true",
        "--net-file",
        str(net_xml),
        "--routes",
        str(trip_output_after),
        "-b",
        str(sim_start_time),
        "-e",
        str(sim_end_time),
        "--additional-files",
        str(additional_xml),
        "--duration-log.statistics",
        "--xml-validation",
        "never",
        "--vehroutes",
        "routes.vehroutes.xml",
        "--no-warnings",
        "--mesosim",
        "true",
        "--seed",
        str(seed),
    ]

    print(f"Running SUMO:\n{' '.join(sumo_cmd)}")
    try:
        subprocess.run(sumo_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to run SUMO simulation: {e}")


def write_trips_to_xml_pretty(trips_df: pd.DataFrame, output_file: Path, attr_cols: list[str]) -> None:
    """
    Write a SUMO-compatible trips XML file from a DataFrame with pretty formatting.

    This function converts a DataFrame containing trip information into an XML file
    that follows the SUMO <trip> format. The output is formatted with indentation 
    and line breaks for improved readability.

    Parameters
    ----------
    trips_df : pd.DataFrame
        DataFrame containing trip data, where each row corresponds to a <trip> entry.
    output_file : Path
        Path to save the formatted trips XML file.
    attr_cols : list of str
        List of column names to include as attributes in each <trip> element.
    """
    def clean_val(x):
        try:
            return str(x)
        except Exception:
            return ""

    # Root <routes> element
    root = ET.Element("routes")

    # Add each trip as a <trip> element
    for _, row in trips_df.iterrows():
        trip_attrs = {col: clean_val(row[col]) for col in attr_cols}
        ET.SubElement(root, "trip", trip_attrs)

    # Convert to string and pretty-print
    rough_string = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="\t", encoding="utf-8")

    # Write to file
    with open(output_file, "wb") as f:
        f.write(pretty_xml)


def update_trip_routes(
    input_trip_file: Path, output_trip_file: Path, routes_df: pd.DataFrame, routes_per_od: str
) -> None:
    """
    Update the trips XML file to align start and end edges with a given route set.

    Parameters
    ----------
    input_trip_file : Path
        Path to the original trips XML file.
    output_trip_file : Path
        Path to save the updated trips XML file.
    routes_df : pd.DataFrame
        DataFrame with ["fromTaz", "toTaz", "start_edge", "last_edge"] columns.
    routes_per_od : str
        Type of routes to use for the simulation (single or multiple).
    """
    # Read trip XML in chunks and combine into a single DataFrame
    all_chunks = []
    for chunk_df in xml2df_str_in_chunks(input_trip_file, "trip"):
        all_chunks.append(chunk_df)

    if all_chunks:
        trips_df = pd.concat(all_chunks, ignore_index=True)
    else:
        print(f"[Warning] No trips found in {input_trip_file.name} — skipping trip update.")
        trips_df = pd.DataFrame(
            columns=[
                "id",
                "depart",
                "from",
                "to",
                "type",
                "fromTaz",
                "toTaz",
                "departLane",
                "departSpeed",
                "depart_float",
            ]
        )

    # Ensure route DataFrame uses string type
    routes_df["fromTaz"] = routes_df["fromTaz"].astype(str)
    routes_df["toTaz"] = routes_df["toTaz"].astype(str)
    routes_df["start_edge"] = routes_df["start_edge"].astype(str)
    routes_df["last_edge"] = routes_df["last_edge"].astype(str)

    # Remove original 'from' and 'to' edges
    trips_df = trips_df.drop(columns=["from", "to"])

    if routes_per_od == "single":
        # Merge correct start and end edges
        trips_df = trips_df.merge(
            routes_df[["fromTaz", "toTaz", "start_edge", "last_edge"]],
            on=["fromTaz", "toTaz"],
            how="inner",
        )
    elif routes_per_od == "multiple":
        # For each unique fromTaz, toTaz pair in trips_df
        for (from_taz, to_taz), group in trips_df.groupby(['fromTaz', 'toTaz']):
            # Filter routes_df for the current fromTaz, toTaz pair
            matching_routes = routes_df[(routes_df['fromTaz'] == from_taz) & (routes_df['toTaz'] == to_taz)].copy()

            # If there are matching routes
            if not matching_routes.empty:
                # Normalize the ratio to sum to 1
                matching_routes['ratio'] = matching_routes['ratio'] / matching_routes['ratio'].sum()
                
                # Assign start_edge and last_edge to trips_df based on the ratio using random selection
                probabilities = matching_routes['ratio'].values
                selected_routes = np.random.choice(matching_routes.index, size=len(group), p=probabilities)

                # Apply the selected routes to the trips_df
                trips_df.loc[group.index, 'start_edge'] = matching_routes.loc[selected_routes, 'start_edge'].values
                trips_df.loc[group.index, 'last_edge'] = matching_routes.loc[selected_routes, 'last_edge'].values

    # Rename columns to SUMO format
    trips_df = trips_df.rename(columns={"start_edge": "from", "last_edge": "to"})

    # Sort trips by departure time
    trips_df["depart_float"] = trips_df["depart"].astype(float)
    trips_df = trips_df.sort_values(by="depart_float")

    # Set departLane to "best" for all trips
    trips_df["departLane"] = "best"

    # Save updated trips to XML
    attr_cols = [
        "id",
        "depart",
        "from",
        "to",
        "type",
        "fromTaz",
        "toTaz",
        "departLane",
        "departSpeed",
    ]

    write_trips_to_xml_pretty(trips_df, output_trip_file, attr_cols)


def create_od_tazrelation_xml(od_df: pd.DataFrame, output_file: Path, od_end_time_seconds: int) -> None:
    """
    Create a TAZ (Traffic Assignment Zone) OD matrix XML file from a DataFrame.

    Parameters
    ----------
    od_df : pd.DataFrame
        DataFrame containing 'from', 'to', and 'count' columns.
    output_file : Path
        Path to save the generated TAZ relation XML file.
    od_end_time_seconds : int
        End time of the simulation in seconds.
    """
    # Step 1: Write raw XML from the DataFrame (root = <interval>)
    od_df.to_xml(
        output_file,
        attr_cols=["from", "to", "count"],
        root_name="interval",
        row_name="tazRelation",
        index=False,
    )

    # Step 2: Add required attributes to <interval> element
    tree = ET.parse(output_file)
    root = tree.getroot()
    root.set("id", "DEFAULT_VEHTYPE")
    root.set("begin", "0")
    root.set("end", str(od_end_time_seconds))

    # Step 3: Wrap <interval> with a new <data> root node
    new_root = ET.Element("data")
    new_root.insert(0, root)
    tree = ET.ElementTree(new_root)

    # Step 4: Overwrite the file with updated root
    tree.write(output_file, encoding="utf-8", xml_declaration=True)

    print(f"Created OD TAZ relation XML at: {output_file}")
