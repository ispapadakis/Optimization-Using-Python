from ortools.sat.python import cp_model
from utils import read_resource_input, read_task_input, read_project_input
import yaml
from datetime import datetime, timedelta
from collections import namedtuple
import sys
import plotly.express as px
import pandas as pd


TaskWindow = namedtuple('TaskWindow', 'start end')
CompletionWin = namedtuple('CompletionWin', 'early tardy')

class Model(object):

    resource_units_per_task = 1

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = cp_model.CpModel()
        self.report_file = "scheduling/{}_report.md".format(name)

    def get_inputs(self, model_input_file: str, date0_str: str):
        rpu_image_file = "scheduling/{}_resource_prior_utilization.png".format(self.name)
        # Import Model Inputs
        with open(model_input_file, 'r') as f:
            model_input = yaml.safe_load(f)

        repfile = open(self.report_file, "w")
        print("## Model Inputs", file=repfile)
        # Set Parameters
        self.datetime_0 = datetime.strptime(date0_str, "%Y-%m-%d")
        self.horizon = model_input['planning_horizon_days']
        self.init_t_max = model_input['resources_possibly_occupied_till']
        self.horizon = model_input['planning_horizon_days']
        self.resources = read_resource_input(
            model_input, 
            self.datetime_0, 
            self.init_t_max, 
            plotfile=rpu_image_file,
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
        print("![Resource Prior Utilization]({} 'Title')".format(rpu_image_file), file=repfile)
        repfile.close()

    def set_model_variables(self):
        self.task_times = {}
        self.task_resource_assign = {}
        self.resource_needs = {resource:[] for resource in self.resources}
        self.resolve_multiple_res = {}
        self.project_completion = {}
        for pname, proj in self.projects.items():
            self.task_times[pname] = []
            self.task_resource_assign[pname] = {}
            self.project_completion[pname] = CompletionWin(
                self.model.NewIntVar(0, self.horizon, "{}_earliness".format(pname)),
                self.model.NewIntVar(0, self.horizon, "{}_tardiness".format(pname))
                )
            for task, duration in proj.task_sequence:
                prefix = "{}_{}_".format(pname,task)
                dv_start = self.model.NewIntVar(0, self.horizon, prefix + 'start')
                dv_end = self.model.NewIntVar(0, self.horizon, prefix + 'end')
                self.task_times[pname].append(TaskWindow(dv_start, dv_end))
                self.task_resource_assign[pname][task] = {}
                res_options = self.task_resource_options[task]
                if len(res_options) == 1:
                    resource = res_options[0]
                    ivname = "{}_{}_interval".format(prefix, resource)
                    dv_interval = self.model.NewIntervalVar(dv_start, duration, dv_end, ivname)
                    self.task_resource_assign[pname][task][resource] = dv_interval
                    self.resource_needs.setdefault(resource,[]).append((dv_interval, self.resource_units_per_task))
                else:
                    for resource in res_options:
                        resprefix = "{}{}_".format(prefix, resource)
                        dv_select = self.model.NewBoolVar(resprefix+"indicator")
                        dv_interval = self.model.NewOptionalIntervalVar(dv_start, duration, dv_end, dv_select, resprefix+"opt_interval")
                        self.task_resource_assign[pname][task][resource] = dv_interval
                        self.resolve_multiple_res.setdefault((pname,task),[]).append(dv_select)
                        self.resource_needs.setdefault(resource,[]).append((dv_interval, self.resource_units_per_task))
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
        # Enforce At Least One Resource Per Task
        for _, idlist in self.resolve_multiple_res.items():
            self.model.AddBoolXOr(*idlist)
        # Disjunctive Constraint: Enforce Resource Capacity Limit Over All Intervals
        for res in self.resources.values():
            ivlist = self.resource_needs[res.name]
            intervals, utilization = zip(*ivlist)
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
        print(self.solver.StatusName())
        print(self.solver.SolutionInfo())
        print("Solver Wall Time {:,.4f} secs".format(self.solver.WallTime()))

    def collect_results(self):
        if self.status == cp_model.OPTIMAL or self.status == cp_model.FEASIBLE:
            print('Solution Status:', self.solver.StatusName())
            self.tograph = []
            for pname in self.task_resource_assign:
                for task in self.task_resource_assign[pname]:
                    for resource, iv in self.task_resource_assign[pname][task].items():
                        start = self.solver.Value(iv.StartExpr())
                        end = self.solver.Value(iv.EndExpr())
                        self.tograph.append({'Project': pname})
                        self.tograph[-1]["Resource"] = resource
                        self.tograph[-1]["Task"] = task
                        self.tograph[-1]["Start"] = self.datetime_0 + timedelta(days=start)
                        self.tograph[-1]["Finish"] = self.datetime_0 + timedelta(days=end)

            print(f'Optimal Objective Value: {self.solver.ObjectiveValue()}')
            print(f'Optimal Objective Bound: {self.solver.BestObjectiveBound()}')
        else:
            print('No solution found.')

    def project_report(self, file=sys.stdout):
        print("\n"*3, file=file)
        print("### Project Completion Report", file=file)
        fmt = "| {:10} | {:>10} | {:>6} | {:>6} |"
        print(fmt.format("Project", "Completion", "Early", "Tardy"), file=file)
        print(fmt.format(":------", "---------:", "----:", "----:"), file=file)
        self.makespan = 0
        for pname in self.projects:
            proj_end = self.solver.Value(self.get_project_endtime(pname))
            earliness, tardiness = self.project_completion[pname]
            self.makespan = max(self.makespan, proj_end)
            print(fmt.format(pname, proj_end, self.solver.Value(earliness), self.solver.Value(tardiness)), file=file)


if __name__ == "__main__":
    mod = Model('scheduling_RD')
    mod.get_inputs(model_input_file='scheduling/RD_Teams_Inputs.yml', date0_str="2023-04-01")
    mod.build_model()
    mod.solve()
    mod.collect_results()
    mod.project_report()

    for pname, task in mod.resolve_multiple_res:
        print(pname, task, [mod.solver.Value(dv) for dv in mod.resolve_multiple_res[pname, task]])
        print(pname, task, mod.task_resource_options[task])



