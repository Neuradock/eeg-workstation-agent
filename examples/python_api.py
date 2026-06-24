from neuradock_agent.io import read_neuradock_txt
from neuradock_agent.workflows import run_alpha_dynamics


recording = read_neuradock_txt("data_examples/alpha/open_closed_eye2.txt")
run = run_alpha_dynamics(recording, output_root="runs/python_api_alpha")

print(f"Report: {run.report_path}")
print(f"Results: {run.results_path}")
for figure in run.figure_paths:
    print(f"Figure: {figure}")
