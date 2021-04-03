import subprocess


def save_and_open_plt_fig(plt_fig, file_path, close_fig=True):
    plt_fig.savefig(file_path)
    if close_fig:
        plt_fig.close()
    subprocess.call("open {}".format(file_path), shell=True)
