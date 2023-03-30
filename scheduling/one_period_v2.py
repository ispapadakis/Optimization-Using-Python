from ortools.sat.python import cp_model
from utils import read_resource_input, read_task_input, read_project_input
import yaml
from datetime import datetime, timedelta
from collections import namedtuple
import sys
import plotly.express as px
import plotly.io as pio
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

CompletionWin = namedtuple('CompletionWin', 'early tardy')
TaskWin = namedtuple('TaskWin', 'start end')
Task = namedtuple('Task','name resource units interval is_active')

class Model(object):

    resource_units_per_task = 1

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = cp_model.CpModel()
        self.report_file = "scheduling/{}_report.md".format(name)

    def get_inputs(self, model_input_file: str, date0_str: str):
        rpu_image_file = "{}_resource_prior_utilization.png".format(self.name)
        # Import Model Inputs
        with open(model_input_file, 'r') as f:
            model_input = yaml.safe_load(f)

        repfile = open(self.report_file, "w")
        print("## Model Inputs", file=repfile)
        # Set Parameters
        self.datetime_0 = datetime.strptime(date0_str, "%Y-%m-%d").date()
        self.get_date = lambda d: self.datetime_0 + timedelta(days=d)
        self.horizon = model_input['planning_horizon_days']
        self.init_t_max = model_input['resources_possibly_occupied_till']
        self.horizon = model_input['planning_horizon_days']
        self.resources = read_resource_input(
            model_input, 
            self.datetime_0, 
            self.init_t_max, 
            plotfile="scheduling/"+rpu_image_file,
            show_utilization_plot=False
            )
        self.task_resource_options = read_task_input(model_input['resources'])
        self.projects = read_project_input(
            model_input['projects'], 
            model_input['project_type'],
            display_summary=True, 
            display_priorities=True,
            file=repfile
            )
        
        print("\n"*3, file=repfile)
        print("### Resource Utilization At Time 0", file=repfile)
        print("![Resource Prior Utilization]({})".format(rpu_image_file), file=repfile)
        repfile.close()

    def set_model_variables(self):
        self.assign = {}
        self.task_times = {}
        self.resource_needs = {resource:[] for resource in self.resources}
        self.resolve_multiple_res = {}
        self.project_completion = {}

        # Collect New Variables for Task: Start, End, Interval, Select if Optional
        # Collect New Variables for Resource Needs
        for pname, proj in self.projects.items():
            self.assign[pname] = []
            self.task_times[pname] = []
            self.project_completion[pname] = CompletionWin(
                self.model.NewIntVar(0, self.horizon, "{}_earliness".format(pname)),
                self.model.NewIntVar(0, self.horizon, "{}_tardiness".format(pname))
                )
            for task, duration in proj.task_sequence:
                prefix = "{}_{}_".format(pname,task)
                dv_start = self.model.NewIntVar(0, self.horizon, prefix + 'start')
                dv_end = self.model.NewIntVar(0, self.horizon, prefix + 'end')
                self.task_times[pname].append(TaskWin(dv_start, dv_end))
                is_one_resource_task = (len(self.task_resource_options[task]) == 1)
                for resource in self.task_resource_options[task]:
                    if is_one_resource_task:
                        dv_select = None
                        dv_interval = self.model.NewIntervalVar(dv_start, duration, dv_end, "{}{}_interval".format(prefix, resource))
                    else:
                        dv_select = self.model.NewBoolVar("{}{}_indicator".format(prefix, resource))
                        dv_interval = self.model.NewOptionalIntervalVar(
                            dv_start, duration, dv_end, dv_select, "{}{}_opt_interval".format(prefix, resource)
                            )
                        self.resolve_multiple_res.setdefault((pname,task),[]).append(dv_select)
                    self.assign[pname].append(
                        Task(task, resource, self.resource_units_per_task, dv_interval, dv_select)
                    )
                    self.resource_needs[resource].append((dv_interval, self.resource_units_per_task))

        # Account for Additional Needs Due to Initial Commitment
        for res in self.resources.values():
            for t, demand in enumerate(res.state0):
                task = "t{:2d}".format(t)
                ivname = "occupied_{}_{}_interval".format(t,res.name)
                if demand > 0:
                    self.resource_needs.setdefault(res.name,[]).append((self.model.NewIntervalVar(t, 1, t+1, ivname), demand))

    def get_project_endtime(self, projname):
        return self.task_times[projname][-1].end
    
    def set_precedence_constraints(self):
        for task_seq in self.task_times.values():
            # NOTE: ensure len(task_seq) >= 1
            for i in range(len(task_seq)-1):
                self.model.Add(task_seq[i].end <= task_seq[i+1].start)

    def set_resource_constraints(self):
        # Enforce One Resource Per Task
        for _, idlist in self.resolve_multiple_res.items():
            self.model.AddBoolXOr(*idlist)
        # Disjunctive Constraint: Enforce Resource Capacity Limit Over All Intervals
        for res in self.resources.values():
            intervals, utilization = zip(*self.resource_needs[res.name])
            self.model.AddCumulative(intervals, utilization, res.capacity)

    def set_objective(self):
        # Deadline Contraints
        for pname, proj in self.projects.items():
            earliness, tardiness = self.project_completion[pname]
            self.model.Add(proj.deadline + tardiness - earliness == self.get_project_endtime(pname))
        # Objective: Optimize Penalty / Bonus
        self.model.Minimize(
            sum(
                proj.delay_penalty * self.project_completion[pname].tardy 
                - proj.early_bonus * self.project_completion[pname].early
                for pname, proj in self.projects.items()
            ))

    def build_model(self):
        self.set_model_variables()
        self.set_precedence_constraints()
        self.set_resource_constraints()
        self.set_objective()

    def solve(self, max_time: int=100):
        self.solver = cp_model.CpSolver()
        # Set Processing Time Limit
        self.solver.parameters.max_time_in_seconds = max_time
        self.status = self.solver.Solve(self.model)
        print(self.solver.ResponseStats())

    def collect_results(self):
        out = "\n"*3
        if self.status == cp_model.OPTIMAL or self.status == cp_model.FEASIBLE:
            out += '- Solution Status: {}\n'.format(self.solver.StatusName())
            self.__tograph__ = []
            for pname in self.assign:
                for tstruct in self.assign[pname]:
                    start = tstruct.interval.StartExpr()
                    end = tstruct.interval.EndExpr()
                    row = {'Project': pname}
                    row["Task"] = tstruct.name
                    row["Resource"] = tstruct.resource
                    row["Start"] = self.get_date(self.solver.Value(start))
                    row["Finish"] = self.get_date(self.solver.Value(end))
                    row["Is_Active"] = True if tstruct.is_active is None else bool(self.solver.Value(tstruct.is_active))
                    self.__tograph__.append(row)

            df = pd.DataFrame(self.__tograph__)
            fig = px.timeline(
                df.loc[df["Is_Active"],:], 
                x_start="Start", 
                x_end="Finish", 
                y="Project", 
                color="Task",
                pattern_shape="Resource",
                pattern_shape_sequence=["x", "", "+"],
                color_discrete_sequence=px.colors.qualitative.Light24
            )
            fig.update_yaxes(categoryorder="category descending")
            pio.write_image(fig, "scheduling/{}_timetable.png".format(self.name), width=1080, height=720)

            out += '\t- Optimal Objective Value: {:,.3f}\n'.format(self.solver.ObjectiveValue())
            out += '\t- Optimal Objective Bound: {:,.3f}\n'.format(self.solver.BestObjectiveBound())
        else:
            out += '- No solution found.\n'
        
        return out

    def project_report(self):
        out = "\n"*3
        out += "### Project Completion Report\n"
        fmt = "| {:10} | {:>10} | {:>6} | {:>6} |\n"
        out += fmt.format("Project", "Completion", "Early", "Tardy")
        out += fmt.format(":------", "---------:", "----:", "----:")
        self.makespan = 0
        for pname in self.projects:
            proj_end = self.solver.Value(self.get_project_endtime(pname))
            earliness, tardiness = self.project_completion[pname]
            self.makespan = max(self.makespan, proj_end)
            out += fmt.format(pname, proj_end, self.solver.Value(earliness), self.solver.Value(tardiness))
        return out
    
    def resource_report(self):
        cols = [(resource, s) for resource in self.resources for s in ['state0','state1']]
        utilization = pd.DataFrame(0, index=np.arange(self.makespan+1), columns=pd.MultiIndex.from_tuples(cols))
        utilization.columns.names = ['Resource','State']
        for res in self.resources.values():
            for i, x in enumerate(res.state0):
                utilization.loc[i,(res.name,'state0')] += x
            for iv, units in self.resource_needs[res.name]:
                start = self.solver.Value(iv.StartExpr())
                end = self.solver.Value(iv.EndExpr())
                for i in range(start,end):
                    utilization.loc[i,(res.name,'state1')] += units
        color_dict = {'state0':'grey', 'state1':'green'}
        utilization.index = [self.get_date(t).strftime("%b %d") for t in utilization.index]
        fig, axs = plt.subplots(len(self.resources), 1, figsize=(8,12), sharex=True)
        fig.autofmt_xdate(rotation=90)
        for i, rname in enumerate(self.resources):
            utilization.loc[:,(rname,'state1')] -= utilization.loc[:,(rname,'state0')]
            utilization[rname].plot.bar(stacked=True, title=rname, width=1, grid=True, color=color_dict, ax=axs[i])
        return fig
    
    def report_results(self):
        repfile = open(self.report_file, "a")
        print("# Optimization Results", file=repfile)
        print(self.collect_results() , file=repfile)
        print(self.project_report() , file=repfile)
        print("## Optimal Timetable" , file=repfile)
        timetable_file = "{}_timetable.png".format(self.name)
        print("![Timetable]({})\n\n\n".format(timetable_file) , file=repfile)
        print("## Optimal Resource Utilization" , file=repfile)
        utilization_file = "{}_utilization.png".format(self.name)
        fig = self.resource_report()
        fig.savefig("scheduling/{}".format(utilization_file), dpi=72)
        print("![Utilization]({})\n\n\n".format(utilization_file) , file=repfile)
        repfile.close()


if __name__ == "__main__":
    mod = Model('scheduling_RD_v2')
    mod.get_inputs(model_input_file='scheduling/RD_Teams_Inputs.yml', date0_str="2023-04-01")
    mod.build_model()
    mod.solve()
    mod.report_results()

