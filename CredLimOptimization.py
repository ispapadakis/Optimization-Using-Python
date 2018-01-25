# -*- coding: utf-8 -*-
# ---
# title: "Credit Limit Optimization Model"
# author: "Yanni Papadakis"
# ---
# Reimplementing R - lpSolveAPI Based - Model


# Import PuLP modeler functions

import pulp as mp

# INPUT PARAMETERS --------------------------------------------------------

# Parameter File 1
# <File Contents>
# size          Applicant Company Size (based on Number of Employees)
# risk          Applicant Company Risk Segment (based on Scorecard)
# credlim       Applicant Company Credit Limit Assigned (based on Historical Accounts Receivable Total)
# n             Companies in Segment
# wotot         Exp Total Writeoff Amount in Segment
# wodiff_mr     Reduction in Exp Writeoff Amount in Segment After Manual Review
# expneed       Expected Total Credit Need Given Credit Limit
# exprev        Expected Revenue from Segment
# cum_n         Cumulative Count of Applicants (Sums Segments with Lower Limit)
# cum_wotot     Cumulative Writeoff Total (Sums Segments with Lower Limit)
# cum_wodiff_mr Cumulative Reduction in Exp Writeoff Amount After Manual Review (Sums Segments with Lower Limit)
# cum_expneed   Cumulative Expected Credit Need Given Credit Limit (Sums Segments with Lower Limit)
# over_exprev   Cumulative Expected Revenue from Segment (Sums Segments with Lower Limit)
with open("clo_pulp_data.csv") as f:
    # Load Title Line
    ttl = f.readline().rstrip().split(',')
    varType = [str,str,float,int,float,float,float,float,int,float,float,float,float]
    rawData = dict()
    for line in f:
        lstr = line.rstrip().split(',')
        l = list(map(lambda f,x: f(x),varType,lstr))
        rawData[tuple(l[:3])] = dict(zip(ttl[3:],l[3:]))

# Scale Parameters in File 1
#   by a thousand
varsScale = {x:1e-3 for x in 
   ("n","cum_n")}
#   by a million
varsScale.update({x:1e-6 for x in 
    ('wotot','wodiff_mr','expneed','exprev','cum_wotot','cum_wodiff_mr','cum_expneed','cum_exprev')})

def scaleElemByFactor(_d, factorDict):
    from copy import deepcopy
    d = deepcopy(_d)
    for k in factorDict:
        d[k] *= factorDict[k]
    return d

scaledData = dict()
for k in rawData:
    scaledData[k] = scaleElemByFactor(rawData[k], varsScale)
  
# Parameter File 2
# <File Contents>
# size      Company Size in Segment (based on Number of Employees)
# risk      Company Risk in Segment (based on Scorecard)
# wor       Writeoff Ratio
# rvr       Revenue Ratio
# mrwor     Writeoff Ratio if Reviewd Manually
with open("clo_pulp_pars.csv") as f:
    # Load Title Line
    paramNames = f.readline().rstrip().split(',')
    paramData = dict()
    paramType = [str,str,float,float,float]
    for line in f:
        lstr = line.rstrip().split(',')
        l = list(map(lambda f,x: f(x),paramType,lstr))
        paramData[tuple(l[:2])] = dict(zip(paramNames[2:],l[2:]))

# Other Parameters

# ManualReview Percent Limit
mrLimit = 0.05

# Max Expected Writeoff Percent Limit
maxwoLimit = 0.5

# Include Cases if Revenue Rate > min(Writeoff Rate, MR Writeoff Rate) [MR Writeoff Rate is Always Min]

# Combinations Accepted
combAcceptable = [comb for comb in paramData if paramData[comb]['mrworate'] < paramData[comb]['revrate']]

# Reduce Data Frame to Acceptable Cases Only - Use Scaled Values
modelData = dict((comb,scaledData[comb]) for comb in scaledData if comb[:2] in combAcceptable)

# List of Model Cases
casesInModel = modelData.keys()
# Cases By (Size,Risk) Combination
caseComb = dict()
for comb in combAcceptable:
    caseComb[comb] = sorted(case for case in casesInModel if case[:2] == comb)

                
# Max Total Clients to Manually Review (as limit of acceptable cases)
am = int( mrLimit * sum(modelData[case]['n'] for case in modelData) * 1000) / 1000

# Max Expected Writeoff (as limit out of all current cases)
wr = int( maxwoLimit * sum(rawData[case]['wotot'] for case in rawData)) * 1e-6


# Problem Variable Definition  
# Minimize Revenue Lost and Expected Writeoff
#   Revenue Lost: Credit Need Over Credit Limit
#   Exp. Writeoff: Expected Writeoff if Within Limit (given in input data)     
prob = mp.LpProblem("Credit Limit Optimization",mp.LpMaximize)

# Declare Variables

# Binary Variable X: Accept Group Automatically
x = mp.LpVariable.dicts("In",casesInModel,0,1,mp.LpBinary)

# Binary Variable Y: Direct Group to Manual Review
y = mp.LpVariable.dicts("MR",casesInModel,0,1,mp.LpBinary)

# Declare Objective Function (Needs to be first equation in model)

# OBJECTIVE: Maximize Revenue by Segment Selection
prob += sum(modelData[case]['exprev'] * x[case] for case in casesInModel), "Exp Revenue Objective"

# SUBJECT TO:

# Constraint: Maximum Manual Review
prob += sum(modelData[case]['cum_n'] * y[case] for case in casesInModel) <= am, "Lim Manual Total"

# Constraint: Select One Only X Per (Size,Risk) Combination
for comb in combAcceptable:
    prob += sum(x[case] for case in caseComb[comb]) <= 1, "Lim 1 X {}".format(comb)

# Constraint: Select One Only Y Per (Size,Risk) Combination
for comb in combAcceptable:
    prob += sum(y[case] for case in caseComb[comb]) <= 1, "Lim 1 Y {}".format(comb)

# Constraint: Selected X Level Exceeds Y Level (MR In Addition to Auto Selection)
for comb in combAcceptable:
    prob += sum(x[case] - y[case] for case in caseComb[comb]) >= 0, "X > Y {}".format(comb)

# Constraint: Maximum Total Risk Exposure
prob += sum([modelData[case]['cum_wotot'] * x[case] - modelData[case]['cum_wodiff_mr'] * y[case] for case in casesInModel]) <= wr, "Lim WO Total Auto"

    
# The problem data is written to an .lp file
prob.writeLP("clo_pulp.lp")

# The problem is solved using PuLP's choice of Solver
prob.solve()

# Obtain Solution
for v in prob.variables():
    if v.varValue > 0: print(v.name, "=", v.varValue)

# Problem Status
print('\n\nProblem',prob.name)
print("Status:", mp.LpStatus[prob.status])
print('Solution Time: {:.1f} sec'.format(prob.solutionTime))
print('Objective Value: ${:.2f} million'.format(prob.objective.value()))
    
# Solution Reports
solnAuto = {i[:2]:i[2] for i in x if x[i].varValue}
solnMR = {i[:2]:i[2] for i in x if y[i].varValue}
sizeseg = sorted({s for s,_ in combAcceptable})
riskseg = list('LMH')
tblAuto = [[solnAuto[(s,r)] if (s,r) in solnAuto else 0.0 for r in riskseg] for s in sizeseg]
tblMR = [[solnMR[(s,r)] if (s,r) in solnMR else 0.0 for r in riskseg] for s in sizeseg]

fmtTtl  = '{:3s} ' + ' {:>6}'*3
fmtLine = '{:3s} ' + ' {:6.0f}'*3
print('\nOptimal Credit Limits AUTO')
print(fmtTtl.format(*list(' LMH')))
for i,s in enumerate(sorted(sizeseg)):
    print(fmtLine.format(s,*tblAuto[i]))
print('\nOptimal Credit Limits MR')
print(fmtTtl.format(*list(' LMH')))
for i,s in enumerate(sorted(sizeseg)):
    print(fmtLine.format(s,*tblMR[i]))
    
print('\nManual Review Requirement (1,000)')
optmr = sum(modelData[case]['cum_n'] * y[case].varValue for case in casesInModel)
print('Optimal {:.3} vs Limit {:.3}'.format(optmr,am))
    
print('\nTotal Exposure to Writeoffs ($M)')
optwo = sum([modelData[case]['cum_wotot'] * x[case].varValue - modelData[case]['cum_wodiff_mr'] * y[case].varValue for case in casesInModel])
print('Optimal {:.3} vs Limit {:.3}'.format(optwo,wr))
