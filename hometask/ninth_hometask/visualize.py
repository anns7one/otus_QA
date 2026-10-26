import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns


def plot_metrics(metrics: dict, out_path="artifacts/metrics.png"):
    names = list(metrics.keys())
    values = list(metrics.values())

    fig, ax = plt.subplots()
    sns.barplot(x=names, y=values, ax=ax)
    ax.set_ylim(0, 1)
    ax.set_title("Качество модели предсказания падения теста")
    fig.savefig(out_path)
    plt.close(fig)
