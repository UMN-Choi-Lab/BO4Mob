# Standard library imports
import argparse
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def sort_routes_by_depart(route_file_path: Path, sorted_output_path: Optional[Path] = None):
    """
    Sort vehicles in a SUMO routes XML file by 'depart' time.

    Parameters
    ----------
    route_file_path : Path
        Path to the input .rou.xml or .vehroutes.xml file.
    sorted_output_path : Optional[Path]
        Path to save the sorted output file. If None, the original file will be overwritten.
    """
    route_file_path = Path(route_file_path)
    if sorted_output_path is None:
        sorted_output_path = route_file_path

    tree = ET.parse(route_file_path)
    root = tree.getroot()

    vehicles = [elem for elem in root.findall("vehicle")]

    # Sort vehicles by 'depart' attribute (convert to float for correct ordering)
    vehicles.sort(key=lambda v: float(v.get("depart", 0)))

    # Remove all existing vehicle elements
    for v in root.findall("vehicle"):
        root.remove(v)

    # Append sorted vehicles back
    for v in vehicles:
        root.append(v)

    # Save the sorted XML
    tree.write(sorted_output_path, encoding="utf-8", xml_declaration=True)
    print(f"[Info] Sorted routes saved to: {sorted_output_path}")


def run_sumo_gui(
    experiment_path: Path,
    epoch: int,
    batch: int,
    network_name: str,
    overwrite: bool = False,
):
    """
    Launch SUMO-GUI for a specific epoch and batch.

    Parameters
    ----------
    experiment_path : Path
        Path to the output/simulation folder.
    epoch : int
        Epoch index number.
    batch : int
        Batch index number.
    network_name : str
        Name of the network folder to locate net.xml and additional.xml.
    overwrite : bool
        Whether to overwrite the original route file or create a sorted copy.
    """
    experiment_path = Path(experiment_path)

    # Define file paths
    base_filename = "result" if epoch == 0 and batch == 0 else f"opt_{epoch}_{batch}"
    route_file = experiment_path / f"simulation/{base_filename}_routes.vehroutes.xml"

    # Determine sorted route file path
    if overwrite:
        sorted_route_file = route_file
    else:
        sorted_route_file = experiment_path / f"simulation/{base_filename}_routes_sorted.vehroutes.xml"

    # Locate the network folder containing net.xml and additional.xml
    network_folder = next(
        (folder for folder in Path("network").rglob("*") if network_name in folder.name),
        None,
    )
    if not network_folder:
        raise FileNotFoundError(f"Network folder containing '{network_name}' not found.")

    net_file = network_folder / "net.xml"
    additional_file = network_folder / "additional.xml"

    # Check existence
    if not route_file.exists():
        raise FileNotFoundError(f"Route file not found: {route_file}")
    if not net_file.exists():
        raise FileNotFoundError(f"Network file not found: {net_file}")
    if not additional_file.exists():
        raise FileNotFoundError(f"Additional file not found: {additional_file}")

    # Sort the route file
    sort_routes_by_depart(route_file, sorted_output_path=sorted_route_file)

    # Modify additional.xml (fixed name)
    modified_additional_file = modify_additional_file_to_gui_version(additional_file)

    # Prepare SUMO-GUI command
    sumo_gui_cmd = [
        "sumo-gui",
        "-n",
        str(net_file),
        "-r",
        str(sorted_route_file),
        "--additional-files",
        str(modified_additional_file),
        "--duration-log.disable",
        "true",
        "--no-warnings",
        "--start",
    ]

    print("[Info] Running SUMO-GUI...")
    subprocess.run(sumo_gui_cmd)

    # Clean up
    cleanup_additional_for_gui(modified_additional_file)


def modify_additional_file_to_gui_version(original_path: Path) -> Path:
    """
    Modify additional.xml for GUI.

    Creates a modified copy of additional.xml named 'additional_for_gui.xml'
    with <edgeData> entries removed.
    """
    tree = ET.parse(original_path)
    root = tree.getroot()

    # Remove all edgeData elements
    for edge_data in root.findall("edgeData"):
        root.remove(edge_data)

    modified_path = original_path.parent / "additional_for_gui.xml"
    tree.write(modified_path, encoding="utf-8", xml_declaration=True)
    return modified_path


def cleanup_additional_for_gui(modified_path: Path):
    """Delete the temporary modified additional_for_gui.xml file."""
    if modified_path.exists():
        modified_path.unlink()


def main():
    """
    Entry point for launching SUMO-GUI.

    Parses CLI arguments, finds the matching simulation folder, and launches SUMO-GUI accordingly.
    """
    parser = argparse.ArgumentParser(description="Launch SUMO-GUI for a specific epoch result.")
    parser.add_argument(
        "--mode",
        type=str,
        choices=['single_od_run', 'full_optimization'],
        required=True,
        help="Mode of operation: single_od_run or full_optimization",
    )
    parser.add_argument(
        "--network_name",
        type=str,
        required=True,
        help="Name of the network (e.g., network1)",
    )
    if parser.parse_known_args()[0].mode == "full_optimization":
        parser.add_argument("--model_name", type=str, required=True, help="Name of the model")
        parser.add_argument("--seed", type=int, required=True, help="Seed value (e.g., 42)")
        parser.add_argument("--epoch", type=int, required=True, help="Epoch index (e.g., 1)")
        parser.add_argument("--batch", type=int, required=True, help="Batch index (e.g., 1)")
    else:
        parser.set_defaults(epoch=0, batch=0)
    parser.add_argument("--date", type=int, default=221014, help="Date for simulation")
    parser.add_argument(
        "--hour",
        type=str,
        default="08-09",
        choices=["06-07", "08-09", "17-18"],
        help="Time for simulation",
    )
    parser.add_argument(
        "--routes_per_od",
        type=str,
        default='single',
        choices=["single", "multiple"],
        help="Type of routes to use for the simulation",
    )
    parser.add_argument(
        "--od_input", type=str, required=False, help="OD input type (e.g., 'od_1ramp_csv', 'od_2092-609-386_values')"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite original route file (default: create sorted copy)",
    )

    args = parser.parse_args()

    # Construct the expected folder pattern
    output_path = Path(f"output/{args.mode}")

    # Find folders containing all three components in their names
    if args.mode == "single_od_run":
        matching_folders = [
            folder
            for folder in output_path.rglob("*")
            if (
                f'network_{args.network_name}' in folder.name
                and str(args.date) in folder.name
                and args.hour in folder.name
                and args.routes_per_od in folder.name
                and args.od_input in folder.name
            )
        ]
    elif args.mode == "full_optimization":
        matching_folders = [
            folder
            for folder in output_path.rglob("*")
            if (
                f'network_{args.network_name}' in folder.name
                and args.model_name in folder.name
                and str(args.date) in folder.name
                and args.hour in folder.name
                and args.routes_per_od in folder.name
                and f"seed-{args.seed:02d}" in folder.name
            )
        ]

    if len(matching_folders) != 1:
        if args.mode == "single_od_run":
            raise FileNotFoundError(
                (
                    f"Expected exactly one folder containing '{args.network_name}', "
                    f"'{args.date}', '{args.hour}', '{args.routes_per_od}', and '{args.od_input}', "
                    f"but found {len(matching_folders)}."
                )
            )
        elif args.mode == "full_optimization":
            raise FileNotFoundError(
                (
                    f"Expected exactly one folder containing '{args.network_name}', "
                    f"'{args.model_name}', '{args.date}', '{args.hour}', "
                    f"'{args.routes_per_od}', and 'seed-{args.seed:02d}', "
                    f"but found {len(matching_folders)}."
                )
            )

    experiment_path = matching_folders[0]

    run_sumo_gui(
        experiment_path=Path(experiment_path),
        epoch=args.epoch,
        batch=args.batch,
        network_name=args.network_name,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
