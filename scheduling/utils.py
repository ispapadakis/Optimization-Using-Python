import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import yaml
import sys
from typing import TextIO
import pandas as pd
import numpy as np

# Plot Resource Utilization Diagram
def plot_utilization(resource_reqs: dict, datetime_0: datetime, tmax: int):
    fig, ax = plt.subplots(len(resource_reqs), 1, figsize=(6,10), sharex=True)
    fig.autofmt_xdate(rotation=90)
    for j, resource in enumerate(resource_reqs.keys()):
        y = resource_reqs[resource]
        y = y + [y[-1]]
        x = [datetime_0 + timedelta(days=t) for t in range(len(y))]
        ax[j].step(x, y, where="post");
        ax[j].fill_between(x, y, step="post", alpha=0.4)
        ax[j].grid()
        ax[j].set_title("Prior Engagement of {}".format(resource))
    return fig

# Display Project Tasks
def project_input_summary(projects):
    out = {}
    for name, proj in projects.items():
        for task, duration in proj.task_sequence:
            out.setdefault(name, {})[task] = duration
    df = pd.DataFrame(out)
    df.loc["------------"] = pd.NA
    df.loc["MIN TIME REQ"] = df.sum()
    for name, proj in projects.items():
        df.loc["DEADLINE",name] = proj.deadline
    return df.applymap(lambda x: "" if pd.isnull(x) else int(x)).to_markdown()

# Display Project Priorities
def project_priorities_report(projects):
    out = "### Project Priorities\n"
    fmt = "\n| {:12} | {:>15} | {:>15} |"
    out += fmt.format("Project","Delay Penalty","Early Bonus")
    out += fmt.format(":------","------------:","----------:")
    for name, proj in projects.items():
        out += fmt.format(name, proj.delay_penalty, proj.early_bonus)
    return out

# Read Resource Inputs
def read_resource_input(
        inputdict: dict, 
        datetime_0: datetime, 
        tmax: int,
        plotfile: str,
        show_utilization_plot: bool=True) -> list:
    # Load Resource Data
    out = {}
    for res, rdict in inputdict['resources'].items():
        out[res] = Resource(res, **rdict)

    # Plot Initial Requirements Per Resource
    res_reqs = {res:rstruct.state0 for res, rstruct in out.items()}
    fig = plot_utilization(res_reqs, datetime_0, tmax)
    fig.suptitle("Unavailable Resources", fontweight ="bold")
    plt.savefig(plotfile)
    if show_utilization_plot:
        plt.show()
    plt.close(fig)

    # Return Resource List
    return out

# Read Task Inputs
def read_task_input(resdict: dict):
    task_type = {}
    for resource, rdict in resdict.items():
        for t in rdict['task']:
            task_type.setdefault(t,[]).append(resource)
    return task_type

# Read Project Inputs
def read_project_input(
        projdict: dict, 
        projtypedict: dict,
        display_summary: bool=True, 
        display_priorities: bool=True,
        file: TextIO=sys.stdout) -> list:
    projects = {}
    for proj, pdict in projdict.items():
        tasks = projtypedict[pdict['type']]
        projects[proj] = Project(name=proj, tasks=tasks, **pdict)
    if display_summary:
        print("### Project Summary\n", file=file)
        print(project_input_summary(projects), file=file)
    if display_priorities:
        print("\n"*3, file=file)
        print(project_priorities_report(projects), file=file)
    return projects

# Resource Class
class Resource(object):

    def __init__(self, name, member, state0=None, busy_units=None, **kwargs) -> None:
        self.name = name
        self.capacity = len(member)
        if state0 is None:
            self.state0 = self.get_state0(busy_units)
        else:
            self.state0 = state0

    def get_state0(self, busy_units):
        if busy_units is None:
            return []
        else:
            out = []
            for start, end in busy_units:
                if start >= end:
                    sys.exit("Incorrect Busy Units Assignment in {} for resource {}".format(busy_units, self.name))
                if len(out) < end:
                    out += [0 for _ in range(len(out),end)]
                for i in range(start, end):
                    out[i] += 1
            return out

    def __repr__(self) -> str:
        return "Resource({0.name!r},{0.capacity!r})".format(self)
    
    def __str__(self) -> str:
        return "Res.{0.name}".format(self)
    
class Project(object):

    def __init__(self, name, type, tasks, durations, deadline, delay_penalty, early_bonus) -> None:
        self.name = name
        self.type = type
        self.deadline = deadline
        if early_bonus >= delay_penalty:
            sys.exit("Unexpected Early Bonus {} and Delay Penalty {}".format(early_bonus, delay_penalty))
        self.delay_penalty = delay_penalty
        self.early_bonus = early_bonus
        self.task_sequence = tuple((t,d) for t, d in zip(tasks,durations))

    def __str__(self) -> str:
        return "Proj.{0.name}".format(self)
    
    
if __name__ == "__main__":
    # Import Model Inputs
    with open('scheduling/RD_Teams_Inputs.yml', 'r') as f:
        model_input = yaml.safe_load(f)

    # Set Parameters
    datetime_0 = datetime.strptime("2023-04-01", "%Y-%m-%d")
    init_t_max = model_input['resources_possibly_occupied_till']
    horizon = model_input['planning_horizon_days']
    
    resources = read_resource_input(model_input, datetime_0, init_t_max, plotfile="test.png", show_utilization_plot=False)
    print("Resources")
    print("---------")
    for resname, res in resources.items():
        print(repr(res))

    task_types = read_task_input(model_input['resources'])

    projects = read_project_input(model_input['projects'], model_input['project_type'])
    

        

