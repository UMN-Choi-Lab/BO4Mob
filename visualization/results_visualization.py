import argparse
import numpy as np
import pandas as pd
import os
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter



def main():
    """
    그림을 그리는 함수입니다.
    Run the full optimization pipeline for OD estimation using SUMO.

    This includes parsing arguments, loading configuration and data,
    performing initial search, running the chosen optimizer (e.g., SPSA, SAASBO, etc.),
    and visualizing results such as convergence plots and flow fit plots.
    """
    # =====================
    # Parse command-line arguments
    # =====================
    parser = argparse.ArgumentParser(description="OD Calibration Optimization")
    parser.add_argument(
        "--network_name",
        type=str,
        default="1ramp",
        choices=["1ramp", "2corridor", "3junction", "4smallRegion", "5fullRegion"],
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="spsa",
        choices=["initSearch", "spsa", "vanillabo", "saasbo", "turbo"],
    )
    parser.add_argument("--seed", type=int, default=33, help="Random seed for reproducibility")
    parser.add_argument("--date", type=int, default=221014, help="Date for simulation")
    parser.add_argument(
        "--hour",
        type=str,
        default="08-09",
        choices=["05-06", "08-09", "12-13", "17-18"],
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
        "--cpu_max",
        type=int,
        default=6,
        help="Maximum number of CPU cores for parallel processing",
    )
    args = parser.parse_args()
    print(args)