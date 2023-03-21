import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Resource Utilization Diagram
def plot_utilization(resource_reqs: dict, datetime_0: datetime, tmax: int = 10):
    fig, ax = plt.subplots(len(resource_reqs), 1, figsize=(6,10), sharex=True)
    fig.autofmt_xdate(rotation=90)
    for j, resource in enumerate(resource_reqs):
        y = [0 for _ in range(tmax)]
        for start, end, utilization in resource_reqs[resource]:
            for i in range(start,end):
                y[i+1] += utilization
        x = [datetime_0 + timedelta(days=t) for t in range(len(y))]
        ax[j].step(x, y, where="pre");
        ax[j].fill_between(x, y, step="pre", alpha=0.4)
        ax[j].grid()
        ax[j].set_title("Utilization of Resource {}".format(resource))
    return fig