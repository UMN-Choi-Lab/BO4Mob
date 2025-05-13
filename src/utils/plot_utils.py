# Third-party imports
import matplotlib.pyplot as plt
import numpy as np


def save_convergence_plot(data_set_total, path_opt_detail):
    """
    Save a convergence plot showing the best NRMSE over epochs.

    Parameters
    ----------
    data_set_total : pd.DataFrame
        Full dataset containing simulation results with 'epoch' and 'loss'.
    path_opt_detail : Path
        Directory where the plot will be saved.
    """
    data_set_opt = data_set_total[data_set_total["epoch"] >= 0].reset_index(drop=True)
    data_set_opt_iter_best = data_set_opt.loc[data_set_opt.groupby("epoch")["loss"].idxmin()].reset_index(drop=True)

    x = data_set_opt_iter_best["epoch"]
    y = data_set_opt_iter_best["loss"].cummin()

    plt.figure()
    plt.plot(x, y)
    plt.xlabel("Epoch")
    plt.ylabel("Best NRMSE")
    plt.title("Convergence Plot")
    plt.savefig(path_opt_detail / "BestNRMSE_convergence_plot.png")
    plt.close()


def save_fit_to_gt_plots(data_set_total, sensor_flow_simul, sensor_flow_gt, path_opt_detail, network_name):
    """
    Save fit-to-ground-truth scatter and bar plots for each epoch's best result.

    Parameters
    ----------
    data_set_total : pd.DataFrame
        Full dataset containing simulation results.
    sensor_flow_simul : pd.DataFrame
        Simulated sensor link flow data.
    sensor_flow_gt : pd.DataFrame
        Ground truth sensor link flow data.
    path_opt_detail : Path
        Path to save plots.
    network_name : str
        Name of the network (e.g., '1ramp').
    """
    path_figs = path_opt_detail / "figs"
    path_figs.mkdir(parents=True, exist_ok=True)

    data_set_opt = data_set_total[data_set_total["epoch"] >= 0].reset_index(drop=True)
    data_set_opt_iter_best = data_set_opt.loc[data_set_opt.groupby("epoch")["loss"].idxmin()].reset_index(drop=True)
    opt_result_best = data_set_opt_iter_best.copy()
    opt_result_best["best_value"] = opt_result_best["loss"].expanding().min()
    opt_result_best = opt_result_best[opt_result_best["loss"] == opt_result_best["best_value"]].drop(
        columns=["best_value"]
    )

    for idx, row in opt_result_best.iterrows():
        if idx > 0:
            curr_epoch = int(row["epoch"])
            curr_batch = int(row["batch"])  # noqa: F841

            curr_sensor_flow_simul = sensor_flow_simul.query("epoch == @curr_epoch and batch == @curr_batch")[
                ["link_id", "interval_nVehContrib"]
            ]

            sensor_flow_merged = sensor_flow_gt.merge(
                curr_sensor_flow_simul,
                on="link_id",
                how="left",
                suffixes=("_gt", "_simul"),
            )

            max_val = max(
                sensor_flow_merged.interval_nVehContrib_gt.max(),
                sensor_flow_merged.interval_nVehContrib_simul.max(),
            )
            vec = np.arange(max_val)

            plt.figure()
            plt.plot(vec, vec, "r-")
            plt.plot(
                sensor_flow_merged.interval_nVehContrib_gt,
                sensor_flow_merged.interval_nVehContrib_simul,
                "x",
            )
            plt.title(f"Epoch {curr_epoch}, Loss: {row['loss']:.4f}")
            plt.xlabel("GT link flows")
            plt.ylabel("Simulated link flows")
            plt.savefig(path_figs / f"{curr_epoch}_fit_to_GT_link_flows.png")
            plt.close()

            if network_name == "1ramp":
                gt_od_vals = np.array(
                    [
                        sensor_flow_gt.loc[
                            sensor_flow_gt["link_id"] == "848489711",
                            "interval_nVehContrib",
                        ].values[0],
                        sensor_flow_gt.loc[
                            sensor_flow_gt["link_id"] == "848489711",
                            "interval_nVehContrib",
                        ].values[0]
                        - sensor_flow_gt.loc[
                            sensor_flow_gt["link_id"] == "848489712",
                            "interval_nVehContrib",
                        ].values[0],
                        sensor_flow_gt.loc[
                            sensor_flow_gt["link_id"] == "95265016#1",
                            "interval_nVehContrib",
                        ].values[0]
                        - sensor_flow_gt.loc[
                            sensor_flow_gt["link_id"] == "848489711",
                            "interval_nVehContrib",
                        ].values[0],
                    ]
                )
                curr_od = (
                    data_set_total.query("epoch == @curr_epoch and batch == @curr_batch")
                    .iloc[0][[col for col in data_set_total.columns if "x_" in col]]
                    .values
                )

                width = 0.35

                plt.figure()
                plt.bar(np.arange(len(curr_od)), curr_od, width, label="Simul")
                plt.bar(np.arange(len(gt_od_vals)) + width, gt_od_vals, width, label="GT")
                plt.legend()
                plt.xlabel("OD Pair")
                plt.ylabel("Demand")
                plt.title(f"OD Demand Comparison (Epoch {curr_epoch})")
                plt.savefig(path_figs / f"{curr_epoch}_OD_bar_plot.png")
                plt.close()
    # Save the best result epoch and batch information to a text file
    best_epoch = int(opt_result_best.iloc[-1]["epoch"])
    best_batch = int(opt_result_best.iloc[-1]["batch"])
    with open(path_opt_detail / f"Best result at epoch {best_epoch}, batch {best_batch}.txt", "w") as f:
        f.write(f"Lowest NRMSE observed at epoch: {best_epoch}, batch: {best_batch}")


def save_fit_to_gt_plots_single_run(x, sensor_flow_gt, curr_link_stats, path_run_detail, network_name):
    """
    Save plots comparing simulation results from a single run to ground truth.

    Parameters
    ----------
    x : np.ndarray
        Simulated OD values.
    sensor_flow_gt : pd.DataFrame
        Ground truth sensor data.
    curr_link_stats : pd.DataFrame
        Simulated sensor data.
    path_run_detail : Path
        Directory to save plots.
    network_name : str
        Name of the network (e.g., '1ramp').
    """
    path_figs = path_run_detail / "figs"
    path_figs.mkdir(parents=True, exist_ok=True)

    sensor_flow_gt_sorted = sensor_flow_gt.sort_values(by="link_id").reset_index(drop=True)
    curr_link_stats_sorted = curr_link_stats.sort_values(by="link_id").reset_index(drop=True)

    if len(sensor_flow_gt_sorted) != len(curr_link_stats_sorted):
        raise ValueError("Mismatch in the number of rows between ground truth and simulated data.")

    if not sensor_flow_gt_sorted["link_id"].equals(curr_link_stats_sorted["link_id"]):
        raise ValueError("Mismatch in link_id values between ground truth and simulated data.")

    max_val = max(
        0,
        max(
            sensor_flow_gt_sorted["interval_nVehContrib"].max(),
            curr_link_stats_sorted["interval_nVehContrib"].max(),
        ),
    )
    vec = np.arange(max_val)

    plt.figure()  # figsize=(10, 6)
    plt.plot(vec, vec, "r-")
    plt.plot(
        sensor_flow_gt_sorted["interval_nVehContrib"],
        curr_link_stats_sorted["interval_nVehContrib"],
        "x",
    )
    plt.xlabel("GT link flows")
    plt.ylabel("Simulated link flows")
    plt.title("Scatter Plot of Ground Truth vs Simulated Link Flows")
    plt.savefig(path_figs / "fit_to_GT_link_flows.png")
    plt.close()

    if network_name == "1ramp":
        gt_od_vals = np.array(
            [
                sensor_flow_gt.loc[sensor_flow_gt["link_id"] == "848489711", "interval_nVehContrib"].values[0],
                sensor_flow_gt.loc[sensor_flow_gt["link_id"] == "848489712", "interval_nVehContrib"].values[0]
                - sensor_flow_gt.loc[sensor_flow_gt["link_id"] == "848489711", "interval_nVehContrib"].values[0],
                sensor_flow_gt.loc[sensor_flow_gt["link_id"] == "95265016#1", "interval_nVehContrib"].values[0]
                - sensor_flow_gt.loc[sensor_flow_gt["link_id"] == "848489711", "interval_nVehContrib"].values[0],
            ]
        )

        width = 0.35

        plt.figure()
        plt.bar(np.arange(len(x)), x, width, label="Simul")
        plt.bar(np.arange(len(gt_od_vals)) + width, gt_od_vals, width, label="GT")
        plt.legend()
        plt.xlabel("OD Pair")
        plt.ylabel("Demand")
        plt.title("OD Demand Comparison")
        plt.savefig(path_figs / "OD_bar_plot.png")
        plt.close()
