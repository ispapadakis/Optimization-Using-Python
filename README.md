# Optimization-Using-Python

## Early Work Using Open Source Solutions

- scipy.optimize is not the best option for problems larger than toy-size

  See: [Example of Nonlinear Optimization Using scipy.optimize](NonlinearProgrammingUsingPython.ipynb)

- The following Python packages are open source and do the job:
  - [Pulp](https://coin-or.github.io/pulp/) - See toy example: [Optimization Using Python/Pulp](CredLimOptimization.py)
  - [Python-MIP](https://www.python-mip.com/) - Find Many Examples in Docs
  - [Google OR-Tools](https://pypi.org/project/ortools/) is an impressive open-source application, lacking good developer support though.

## Constraint Programming

Of particular interest is the cpModel solver for Contraint Programming found in **ortools**. See examples below:

- [Job Shop Scheduling (Constraint Programming)](SimpleJobShopScheduling.ipynb)

- [One Period Planner for R&D Project Scheduling (Constraint Programming)](examples/schedV2/one_period_v2_example_report.md)
  - [Code](scheduling/one_period_v2.py)
  - Leverages AddCumulative Constraint to set Capacity Limit over Project Horizon.
  - **Minimize**: Resource Cost + Tardiness Penalty - Early Completion Bonus
  - Resources May Compete for Tasks.
  - Expensive Resources Might Finish Tasks Earlier Than Inexpensive Ones.
  - Input Data in .csv Format.
