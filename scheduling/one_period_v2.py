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

    def get_inputs(self):
        # Import Model Inputs
        with open("scheduling/{}.yml".format(self.name), 'r') as f:
            model_input = yaml.safe_load(f)

        self.project_attrs = pd.read_csv(model_input['project_attrs'], index_col=[0])
        self.projects = self.project_attrs.index.to_list()
        self.project_reqs = pd.read_csv(model_input['project_reqs'], index_col=[0,1,2])
        self.resource_attrs = pd.read_csv(model_input['resource_attrs'], index_col=[0])
        self.resource_busy = pd.read_csv(model_input['resource_busy'], index_col=[0])
        self.task_choice = self.project_reqs.groupby(['Project','Task']).size()
        self.resources = self.resource_attrs.index.to_list()
        # Upper Limit for Project Completion
        self.horizon = self.project_reqs["Duration"].sum() + len(self.resource_busy)
        self.report_path = model_input["report_path"]

        self.report_file = self.report_path.format(self.name+"_report.md")
        repfile = open(self.report_file, "w")
        print("## Model Inputs", file=repfile)
        print("\n\n### Project Attributes\n", file=repfile)
        self.project_attrs.to_markdown(repfile)
        print("\n\n### Project Requirements\n", file=repfile)
        self.project_reqs.reset_index().to_markdown(repfile, index=False)        
        print("\n\n### Resource Attributes\n", file=repfile)
        self.resource_attrs.to_markdown(repfile)
        print("\n\n### Resources Busy at Time 0\n", file=repfile)
        self.resource_busy.plot.bar(width=1,subplots=True, figsize=(10,7), sharex=True)
        state0fig = self.name + "_state0.png"
        plt.savefig(self.report_path.format(state0fig))
        plt.close()
        print("![Utilization At Time 0]({})".format(state0fig), file=repfile)
        # Set Parameters
        self.datetime_0 = datetime.strptime(model_input["date0_str"], "%Y-%m-%d").date()
        self.get_date = lambda d: self.datetime_0 + timedelta(days=d)
        repfile.close()

    def set_model_variables(self):

        # Project Earliness and Tardiness
        self.project_completion = {}
        for pname in self.projects:
            self.project_completion[pname] = CompletionWin(
                self.model.NewIntVar(0, self.horizon, "{}_earliness".format(pname)),
                self.model.NewIntVar(0, self.horizon, "{}_tardiness".format(pname))
                )
            
        # Collect New Variables for Task: Start, End, Interval, Select if Optional
        # Collect New Variables for Resource Needs
        self.task_times = {}
        self.assign = {}
        self.resource_needs = {resource:[] for resource in self.resources}
        self.chooce_resource = {}

        for (project, task), pdata in self.project_reqs.groupby(["Project","Task"], sort=False):
            task_label = "{}_{}_".format(project,task)
            dv_start = self.model.NewIntVar(0, self.horizon, task_label + 'start')
            dv_end = self.model.NewIntVar(0, self.horizon, task_label + 'end')
            self.task_times.setdefault(project, []).append(TaskWin(dv_start, dv_end))
            has_multiple_options = (len(pdata) > 1)
            for resource in pdata.index.get_level_values("Resource"):
                resource_label = "{}_{}_{}_".format(project, task, resource)
                duration = self.project_reqs.loc[(project,task,resource),"Duration"]
                units = self.project_reqs.loc[(project,task,resource),"Units"]
                if has_multiple_options:
                    dv_select = self.model.NewBoolVar(resource_label + "indicator")
                    dv_interval = self.model.NewOptionalIntervalVar(
                            dv_start, duration, dv_end, dv_select, resource_label + "interval"
                            )
                    self.chooce_resource.setdefault((project,task),[]).append(dv_select)
                else:
                    dv_select = None
                    dv_interval = self.model.NewIntervalVar(dv_start, duration, dv_end, resource_label + "_interval")
                self.assign.setdefault(project, []).append(Task(task, resource, units, dv_interval, dv_select))
                self.resource_needs.setdefault(resource, []).append((dv_interval, units))

        # Account for Additional Needs Due to Initial Commitment
        for resource in self.resources:
            for t, demand in enumerate(self.resource_busy[resource].values):
                task = "t{:2d}".format(t)
                ivname = "occupied_{}_{}_interval".format(t,resource)
                if demand > 0:
                    self.resource_needs.setdefault(resource,[]).append((self.model.NewIntervalVar(t, 1, t+1, ivname), demand))

    def get_project_endtime(self, projname):
        return self.task_times[projname][-1].end
    
    def set_precedence_constraints(self):
        for task_seq in self.task_times.values():
            # NOTE: ensure len(task_seq) >= 1
            for i in range(len(task_seq)-1):
                self.model.Add(task_seq[i].end <= task_seq[i+1].start)

    def set_resource_constraints(self):
        # Enforce One Resource Per Task
        for _, idlist in self.chooce_resource.items():
            self.model.AddBoolXOr(*idlist)
        # Disjunctive Constraint: Enforce Resource Capacity Limit Over All Intervals
        for resource in self.resources:
            intervals, utilization = zip(*self.resource_needs[resource])
            self.model.AddCumulative(
                intervals, 
                utilization, 
                self.resource_attrs.loc[resource, "Capacity"]
                )

    def set_objective(self):
        # Deadline Contraints
        for project in self.projects:
            deadline = self.project_attrs.loc[project,"Deadline"]
            earliness, tardiness = self.project_completion[project]
            self.model.Add(deadline + tardiness - earliness == self.get_project_endtime(project))
        # Objective: Minimize Resource Cost + Delay Penalty - Early Bonus
        resource_cost = []
        for project in self.projects:
            for tstruct in self.assign[project]:
                cpd = self.resource_attrs.loc[tstruct.resource, "Cost per Day"]
                duration = tstruct.interval.SizeExpr()
                cost_per_task = cpd * tstruct.units * duration
                resource_cost.append(cost_per_task if tstruct.is_active is None else cost_per_task * tstruct.is_active)
                
        self.model.Minimize(
            sum(resource_cost) +
            sum(
                pdata["Delay Penalty"] * self.project_completion[project].tardy 
                - pdata["Early Bonus"] * self.project_completion[project].early
                for project, pdata in self.project_attrs.iterrows()
                )
            )

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
            filename = self.report_path.format("{}_timetable.png".format(self.name))
            pio.write_image(fig, filename, width=1080, height=720)

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
        for resource in self.resources:
            for i, x in enumerate(self.resource_busy[resource].values):
                utilization.loc[i,(resource,'state0')] += x
            for iv, units in self.resource_needs[resource]:
                start = self.solver.Value(iv.StartExpr())
                end = self.solver.Value(iv.EndExpr())
                for i in range(start,end):
                    utilization.loc[i,(resource,'state1')] += units
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
        fig.savefig(self.report_path.format(utilization_file), dpi=72)
        print("![Utilization]({})\n\n\n".format(utilization_file) , file=repfile)
        repfile.close()


if __name__ == "__main__":
    mod = Model('one_period_v2_example')
    mod.get_inputs()
    mod.build_model()
    mod.solve()
    mod.report_results()