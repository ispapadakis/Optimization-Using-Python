## Model Inputs


### Project Attributes

| Project   |   Deadline |   Delay Penalty |   Early Bonus |
|:----------|-----------:|----------------:|--------------:|
| longasap  |         33 |               4 |           1   |
| long      |         40 |               3 |           1   |
| regsize   |         38 |               2 |           0.5 |
| short     |         42 |               1 |           0.1 |

### Project Requirements

| Project   | Task                         | Resource   |   Duration |   Units |
|:----------|:-----------------------------|:-----------|-----------:|--------:|
| longasap  | T01_Plan_Project             | Planner    |          2 |       1 |
| longasap  | T02_Design_Exp               | Generative |          2 |       2 |
| longasap  | T02_Design_Exp               | Planner    |          2 |       1 |
| longasap  | T03_Soln_Pass_A              | Generative |          8 |       1 |
| longasap  | T04_Eval_Pass_A              | Generative |          1 |       2 |
| longasap  | T04_Eval_Pass_A              | Planner    |          1 |       1 |
| longasap  | T05_Soln_Pass_B              | Generative |          4 |       1 |
| longasap  | T06_Eval_Pass_B              | Generative |          1 |       1 |
| longasap  | T07_Soln_Pass_C              | Generative |          3 |       1 |
| longasap  | T08_Eval_Pass_C              | Generative |          1 |       1 |
| longasap  | T09_Clinical_Study_Design    | Clinical   |          1 |       1 |
| longasap  | T10_Clinical_Study_Execution | Clinical   |          8 |       1 |
| longasap  | T11_Clinical_Study_Report    | Clinical   |          1 |       2 |
| longasap  | T11_Clinical_Study_Report    | Planner    |          1 |       1 |
| longasap  | T12_Documentation_to_Client  | Planner    |          3 |       1 |
| long      | T01_Plan_Project             | Planner    |          2 |       1 |
| long      | T02_Design_Exp               | Generative |          2 |       2 |
| long      | T02_Design_Exp               | Planner    |          2 |       1 |
| long      | T03_Soln_Pass_A              | Generative |          8 |       1 |
| long      | T04_Eval_Pass_A              | Generative |          1 |       2 |
| long      | T04_Eval_Pass_A              | Planner    |          1 |       1 |
| long      | T05_Soln_Pass_B              | Generative |          4 |       1 |
| long      | T06_Eval_Pass_B              | Generative |          1 |       1 |
| long      | T07_Soln_Pass_C              | Generative |          3 |       1 |
| long      | T08_Eval_Pass_C              | Generative |          1 |       1 |
| long      | T09_Clinical_Study_Design    | Clinical   |          1 |       1 |
| long      | T10_Clinical_Study_Execution | Clinical   |          8 |       1 |
| long      | T11_Clinical_Study_Report    | Clinical   |          1 |       2 |
| long      | T11_Clinical_Study_Report    | Planner    |          1 |       1 |
| long      | T12_Documentation_to_Client  | Planner    |          3 |       1 |
| regsize   | T01_Plan_Project             | Planner    |          2 |       1 |
| regsize   | T02_Design_Exp               | Generative |          2 |       2 |
| regsize   | T02_Design_Exp               | Planner    |          2 |       1 |
| regsize   | T03_Soln_Pass_A              | Generative |          8 |       3 |
| regsize   | T04_Eval_Pass_A              | Generative |          1 |       2 |
| regsize   | T04_Eval_Pass_A              | Planner    |          1 |       1 |
| regsize   | T05_Soln_Pass_B              | Generative |          4 |       3 |
| regsize   | T06_Eval_Pass_B              | Generative |          1 |       1 |
| regsize   | T09_Clinical_Study_Design    | Clinical   |          1 |       1 |
| regsize   | T10_Clinical_Study_Execution | Clinical   |          6 |       1 |
| regsize   | T12_Documentation_to_Client  | Planner    |          3 |       1 |
| short     | T01_Plan_Project             | Planner    |          2 |       1 |
| short     | T02_Design_Exp               | Generative |          2 |       1 |
| short     | T02_Design_Exp               | Planner    |          2 |       1 |
| short     | T03_Soln_Pass_A              | Generative |         12 |       1 |
| short     | T04_Eval_Pass_A              | Generative |          1 |       2 |
| short     | T04_Eval_Pass_A              | Planner    |          1 |       1 |
| short     | T09_Clinical_Study_Design    | Clinical   |          1 |       1 |
| short     | T10_Clinical_Study_Execution | Clinical   |          8 |       1 |
| short     | T11_Clinical_Study_Report    | Clinical   |          1 |       2 |
| short     | T11_Clinical_Study_Report    | Planner    |          1 |       1 |

### Resource Attributes

| Resource   |   Capacity |   Cost per Day |
|:-----------|-----------:|---------------:|
| Planner    |          2 |           1000 |
| Generative |          5 |            700 |
| Clinical   |          3 |            800 |

# Optimization Results



- Solution Status: OPTIMAL
	- Optimal Objective Value: 116,719.000
	- Optimal Objective Bound: 116,719.000




### Project Completion Report
| Project    | Completion |  Early |  Tardy |
| :------    | ---------: |  ----: |  ----: |
| longasap   |         37 |      0 |      4 |
| long       |         40 |      0 |      0 |
| regsize    |         39 |      0 |      1 |
| short      |         43 |      0 |      1 |



## Optimal Timetable
![Timetable](one_period_v2_example_timetable.png)





## Optimal Resource Utilization
![Utilization](one_period_v2_example_utilization.png)



