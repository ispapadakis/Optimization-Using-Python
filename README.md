# Optimization-Using-Python

## Early Work Using Open Source Solutions

- scipy.optimize is not the best option for problems larger than toy-size

See an example here: [Example of Nonlinear Optimization Using scipy.optimize](NonlinearProgrammingUsingPython.ipynb)

- The following Python packages are open source and do the job:
  - [Pulp](https://coin-or.github.io/pulp/) - See toy example: [Optimization Using Python/Pulp](CredLimOptimization.py)
  - [Python-MIP](https://www.python-mip.com/) - Find Many Examples in Docs

## Constraint Programming

[Google OR-Tools](https://pypi.org/project/ortools/) is an impressive open-source application, lacking developer support though.

Of particular interest is the cpModel solver for Contraint Programming. See examples below:

- [Job Shop Scheduling (Constraint Programming)](SimpleJobShopScheduling.ipynb)

- [One Period Planner for R&D Project Scheduling (Constraint Programming)](scheduling/scheduling_RD_report.md)
  - Leverages AddCumulative constraint
  - Some tasks may be completed by multiple resources. Which resources are best of these tasks is chosen by the optimization model.
