from ortools.sat.python import cp_model
import yaml
from datetime import datetime, timedelta
from collections import namedtuple
from itertools import product
import plotly.express as px
import plotly.io as pio
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

CompletionWin = namedtuple('CompletionWin', 'early tardy')
TaskOption = namedtuple('TaskOption','resource interval is_active')
Task = namedtuple('Task', 'task start end options mult')

class Model2P(object):

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = cp_model.CpModel()

    def get_inputs(self):
        "Ingest Input Data"
        # Read Model Configuration Parameters
        with open("scheduling/{}.yml".format(self.name), 'r') as f:
            model_input = yaml.safe_load(f)
        # Read Project and Resource Data
        self.project_attrs = pd.read_csv(model_input['project_attrs'], index_col=[0])
        self.projects = self.project_attrs.index.to_list()
        bau = pd.read_csv(model_input['project_reqs'], index_col=[0,1,2]).sort_index()
        bypass = [tuple(p) for p in model_input['stoch_task']['bypass']]
        self.project_reqs = pd.concat({"BAU":bau, "BYPASS":bau.drop(bypass).copy()}, names=['Scenario'])
        self.resource_attrs = pd.read_csv(model_input['resource_attrs'], index_col=[0])
        self.resource_busy = pd.read_csv(model_input['resource_busy'], index_col=[0])
        self.resources = self.resource_attrs.index.to_list()
        # Read Stochastic Scenario Data
        self.prob = {
            "BAU":(1 - model_input["stoch_task"]['bypass_probability']), 
            "BYPASS": model_input["stoch_task"]['bypass_probability']
            }
        self.uncertainty_resolution = model_input["stoch_task"]['uncertainty_resolves_after']
        # Upper Limit for Project Completion
        self.horizon = self.project_reqs.groupby('Scenario')["Duration"].sum().max() + len(self.resource_busy)
        # Set Report Path and Name
        self.report_path = model_input["report_path"]
        self.report_file = self.report_path.format(self.name+"_report.md")
        # Write Input Data Sections in Report
        repfile = open(self.report_file, "w")
        print("## Model Inputs", file=repfile)
        print("\n\n### Project Attributes\n", file=repfile)
        self.project_attrs.to_markdown(repfile)
        print("\n\n### Project Requirements\n", file=repfile)
        self.project_reqs.reset_index().to_markdown(repfile, index=False)        
        print("\n\n### Resource Attributes\n", file=repfile)
        self.resource_attrs.to_markdown(repfile)
        print("\n\n### Stochastic Attributes\n", file=repfile)
        print("\nBypass Tasks:", file=repfile)
        for tp in model_input["stoch_task"]['bypass']:
            print(*tp, file=repfile)
        print("\nGiven Info After End Of", file=repfile, end=" ")
        print(model_input["stoch_task"]['uncertainty_resolves_after']['project'], file=repfile, end=" ")
        print(model_input["stoch_task"]['uncertainty_resolves_after']['task'], file=repfile)
        print("\nWith Probabilities\n", file=repfile)
        for event, prob in self.prob.items():
            print("Event {:>8} -> Prob {:.1%}".format(event, prob), file=repfile)
        repfile.close()
        # Model Date Utilities
        self.datetime_0 = datetime.strptime(model_input["date0_str"], "%Y-%m-%d").date()
        self.get_date = lambda d: self.datetime_0 + timedelta(days=d)

    def set_model_variables(self):

        # Model Data Structure to Include Completion Times and Resource Choices
        self.assign = dict()
        for scenario, project, task, resource in self.project_reqs.index:
            self.assign.setdefault(scenario, {}).setdefault(project,[])
            if self.assign[scenario][project] and task == self.assign[scenario][project][-1].task:
                tstruct = self.assign[scenario][project][-1]
                self.assign[scenario][project][-1] = \
                    Task(tstruct.task,None,None,tstruct.options+[TaskOption(resource, None, None)],True)
            else:
                self.assign[scenario][project].append(
                    Task(task,None,None,[TaskOption(resource, None, None)],False)
                    )
        # Project Earliness and Tardiness
        self.project_completion = {}
        for scenario, project in product(self.prob.keys(), self.projects):
            self.project_completion[(scenario,project)] = CompletionWin(
                self.model.NewIntVar(0, self.horizon, "{}_{}_earliness".format(scenario, project)),
                self.model.NewIntVar(0, self.horizon, "{}_{}_tardiness".format(scenario, project))
                )
        # Uncertainty Resolution Time
        self.urt = self.model.NewIntVar(0, self.horizon+1, "uncertainty_resolution_time")
        # Collect New Variables for Task: Start, End, Interval, Select if Optional
        # Collect New Variables for Resource Needs
        # Collect Variable for Information Constraints
        self.resource_needs = {resource:[] for resource in self.resources}
        self.completion_time = {}
        self.info_revelation = []

        for scenario, projects in self.assign.items():
            for project, pdata in projects.items():
                new_pdata = []
                for tstruct in pdata:
                    task = tstruct.task
                    task_label = "{}_{}_{}_".format(scenario,project,task)
                    dv_start = self.model.NewIntVar(0, self.horizon, task_label + 'start')
                    dv_end = self.model.NewIntVar(0, self.horizon, task_label + 'end')
                    new_pdata.append(Task(task, dv_start, dv_end, [], tstruct.mult))
                    if project == self.uncertainty_resolution['project'] and task == self.uncertainty_resolution['task']:
                        self.info_revelation.append(dv_end)
                    for rstruct in tstruct.options:
                        resource = rstruct.resource
                        resource_label = "{}_{}_{}_{}_".format(scenario,project,task,resource)
                        duration = self.project_reqs.loc[(scenario,project,task,resource),"Duration"]
                        units = self.project_reqs.loc[(scenario,project,task,resource),"Units"]
                        if tstruct.mult:
                            rt_end = self.model.NewIntVar(0, self.horizon, resource_label + 'end')
                            dv_select = self.model.NewBoolVar(resource_label + "indicator")
                            dv_interval = self.model.NewOptionalIntervalVar(
                                    dv_start, duration, rt_end, dv_select, resource_label + "interval"
                                    )
                            self.completion_time.setdefault((scenario, project, task),[]).append(rt_end)
                        else:
                            dv_select = True
                            dv_interval = self.model.NewIntervalVar(dv_start, duration, dv_end, resource_label + "_interval")
                        new_pdata[-1].options.append(TaskOption(resource, dv_interval, dv_select))
                        self.resource_needs.setdefault((scenario, resource), []).append((dv_interval, units))
                self.assign[scenario][project] = new_pdata

        # Account for Additional Needs Due to Initial Commitment
        for scenario, resource in product(self.prob.keys(), self.resources):
            for t, demand in enumerate(self.resource_busy[resource].values):
                task = "t{:2d}".format(t)
                ivname = "occupied_{}_{}_{}_interval".format(t,scenario,resource)
                if demand > 0:
                    self.resource_needs.setdefault((scenario, resource),[]).append((self.model.NewIntervalVar(t, 1, t+1, ivname), demand))

    def task_gen(self, mult_only=True):
        for scenario, projects in self.assign.items():
            for project, pdata in projects.items():
                for tstruct in pdata:
                    if mult_only and not tstruct.mult:
                        continue
                    yield scenario, project, tstruct

    def get_project_endtime(self, scenario, project):
        return self.assign[scenario][project][-1].end
    
    def set_precedence_constraints(self):
        # Last Resource End Time is Task End Time
        for _, _, tstruct in self.task_gen(mult_only=True):
            self.model.AddMaxEquality(tstruct.end, [rstruct.interval.EndExpr() for rstruct in tstruct.options])
        # Enforce Task Precedence for Each Scenario, Project Combination
        for scenario in self.assign:
            for project in self.assign[scenario]:
                task_seq = self.assign[scenario][project]
                # NOTE: ensure len(task_seq) >= 1
                for i in range(len(task_seq)-1):
                    self.model.Add(task_seq[i].end <= task_seq[i+1].start)

    def set_resource_constraints(self):
        # Enforce One Resource Per Task
        # For Each Scenario, Project, Task Combination Require: Only One Resource <<is_active>> Indicator is True
        for _, _, tstruct in self.task_gen(mult_only=True):
            self.model.AddBoolXOr(rstruct.is_active for rstruct in tstruct.options)
        # Disjunctive Constraint: Enforce Resource Capacity Limit Over All Intervals
        # Assumes Resource Capacity Does Not Vary By Stochastic Scenario
        # Easy to extend model by relaxing this assumption
        for scenario, resource in product(self.prob.keys(), self.resources):
            intervals, utilization = zip(*self.resource_needs[scenario, resource])
            self.model.AddCumulative(
                intervals, 
                utilization, 
                self.resource_attrs.loc[resource, "Capacity"]
                )

    def set_information_constraints(self):
        self.model.AddMaxEquality(self.urt, self.info_revelation)
        self.model.AddMinEquality(self.urt, self.info_revelation)
        for project in self.projects:
            for bau_tstruct, bypass_tstruct in zip(self.assign["BAU"][project], self.assign["BYPASS"][project]):
                min_time = self.model.NewIntVar(0, self.horizon + 1, "")
                precede = self.model.NewBoolVar("")
                self.model.AddMinEquality(min_time, [bau_tstruct.start, bypass_tstruct.start])
                self.model.Add(min_time <= self.urt).OnlyEnforceIf(precede)
                self.model.Add(min_time > self.urt).OnlyEnforceIf(precede.Not())
                self.model.Add(bau_tstruct.start == bypass_tstruct.start).OnlyEnforceIf(precede)
                self.model.Add(bau_tstruct.end == bypass_tstruct.end).OnlyEnforceIf(precede)

    def set_objective(self):
        # Deadline Contraints
        for scenario, project in self.project_completion:
            deadline = self.project_attrs.loc[project,"Deadline"]
            earliness, tardiness = self.project_completion[scenario, project]
            self.model.Add(deadline + tardiness - earliness == self.get_project_endtime(scenario, project))
        # Objective: Minimize Resource Cost + Delay Penalty - Early Bonus
        resource_cost = []
        for scenario, project, tstruct in self.task_gen(mult_only=False):
            for rstruct in tstruct.options:
                cpd = self.resource_attrs.loc[rstruct.resource, "Cost per Day"]
                duration = rstruct.interval.SizeExpr()
                units = self.project_reqs.loc[(scenario,project,tstruct.task,rstruct.resource),"Units"]
                cost_per_task = cpd * units * duration * rstruct.is_active
                resource_cost.append(self.prob[scenario] * cost_per_task)
                
        self.model.Minimize(
            sum(resource_cost) +
            sum(
                prob * (
                    pdata["Delay Penalty"] * self.project_completion[scenario, project].tardy 
                    - pdata["Early Bonus"] * self.project_completion[scenario, project].early
                )
                for project, pdata in self.project_attrs.iterrows()
                for scenario, prob in self.prob.items()
                )
            )

    def build_model(self):
        self.set_model_variables()
        self.set_precedence_constraints()
        self.set_resource_constraints()
        self.set_information_constraints()
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
            for scenario, project, tstruct in self.task_gen(mult_only=False):
                for rstruct in tstruct.options:
                    start = rstruct.interval.StartExpr()
                    end = rstruct.interval.EndExpr()
                    row = {'Scenario': scenario, 'Project': project}
                    row["Task"] = tstruct.task
                    row["Resource"] = rstruct.resource
                    row["Start"] = self.get_date(self.solver.Value(start))
                    row["Finish"] = self.get_date(self.solver.Value(end))
                    row["Is_Active"] = bool(self.solver.Value(rstruct.is_active))
                    self.__tograph__.append(row)

            df = pd.DataFrame(self.__tograph__)
            df["Project_Scenario"] = df.apply(lambda x: "{Project:}_{Scenario:}".format(**x), axis=1)
            fig = px.timeline(
                df.loc[df["Is_Active"],:], 
                x_start="Start", 
                x_end="Finish", 
                y="Project_Scenario", 
                color="Task",
                pattern_shape="Resource",
                pattern_shape_sequence=["x", "", "+"],
                color_discrete_sequence=px.colors.qualitative.Light24
            )
            fig.update_yaxes(categoryorder="category descending")
            urt = self.get_date(self.solver.Value(self.urt))
            fig.add_vline(x=urt, line_dash="dot", line_color="white")
            fig.add_annotation(
                dict(x=urt,y=-1.0,text="Uncertainty Resolution",xanchor='center',font=dict(size=15))
                )
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
        fmt = "| {:10} | {:10} | {:>10} | {:>6} | {:>6} |\n"
        out += fmt.format("Scenario", "Project", "Completion", "Early", "Tardy")
        out += fmt.format(":-------", ":------", "---------:", "----:", "----:")
        self.makespan = {scenario: 0 for scenario in self.prob}
        for scenario, project in product(self.prob.keys(), self.projects):
            proj_end = self.solver.Value(self.get_project_endtime(scenario, project))
            earliness, tardiness = self.project_completion[scenario, project]
            self.makespan[scenario] = max(self.makespan[scenario], proj_end)
            out += fmt.format(scenario, project, proj_end, self.solver.Value(earliness), self.solver.Value(tardiness))

        out += "\n\n### Time Uncertainty Is Resolved\n\n"
        out +=  str(self.get_date(self.solver.Value(self.urt)))
        out +=  " (Or {} Days After Time 0)\n".format(self.solver.Value(self.urt))
        return out
    
    def resource_report(self):
        cols = [(scenario, resource, s) 
                for scenario in self.prob 
                for resource in self.resources 
                for s in ['state0','state1']]
        utilization = pd.DataFrame(0, index=np.arange(max(self.makespan.values())+1), columns=pd.MultiIndex.from_tuples(cols))
        utilization.columns.names = ['Scenario','Resource','State']
        for scenario, resource in product(self.prob.keys(), self.resources):
            for i, x in enumerate(self.resource_busy[resource].values):
                utilization.loc[i,(scenario, resource,'state0')] += x
            for iv, units in self.resource_needs[scenario, resource]:
                start = self.solver.Value(iv.StartExpr())
                end = self.solver.Value(iv.EndExpr())
                for i in range(start,end):
                    utilization.loc[i,(scenario, resource,'state1')] += units
        color_dict = {'state0':'grey', 'state1':'green'}
        utilization.index = [self.get_date(t).strftime("%b %d") for t in utilization.index]
        fig, axs = plt.subplots(len(self.resources), len(self.prob), figsize=(16,12), sharex=True)
        fig.autofmt_xdate(rotation=90)
        urt = self.solver.Value(self.urt)
        for i, rname in enumerate(self.resources):
            for j, scenario in enumerate(self.prob.keys()):
                utilization.loc[:,(scenario, rname,'state1')] -= utilization.loc[:,(scenario, rname,'state0')]
                ttl = "{}_{}".format(scenario, rname)
                utilization[scenario][rname].plot.bar(stacked=True, title=ttl, width=1, grid=True, color=color_dict, ax=axs[i,j])
                yannot = utilization[scenario][rname].sum(1).max()
                axs[i,j].axvline(urt, color='red', linestyle=':', lw=2)
                axs[i,j].text(urt, yannot, "Uncertainty\nResolution", ha='center', va='top', 
                              bbox=dict(facecolor='white',boxstyle='square',edgecolor='red',pad=0.2))
        return fig
    
    def report_results(self):
        repfile = open(self.report_file, "a")
        print("\n\n# Optimization Results", file=repfile)
        print(self.collect_results() , file=repfile)
        print(self.project_report() , file=repfile)
        print("\n\n## Optimal Timetable" , file=repfile)
        timetable_file = "{}_timetable.png".format(self.name)
        print("![Timetable]({})\n\n\n".format(timetable_file) , file=repfile)
        print("\n\n## Optimal Resource Utilization" , file=repfile)
        utilization_file = "{}_utilization.png".format(self.name)
        fig = self.resource_report()
        fig.savefig(self.report_path.format(utilization_file), dpi=72)
        print("![Utilization]({})\n\n\n".format(utilization_file) , file=repfile)
        repfile.close()


if __name__ == "__main__":
    mod = Model2P('stoch_duration_example_V1')
    mod.get_inputs()
    mod.build_model()
    mod.solve()
    mod.report_results()