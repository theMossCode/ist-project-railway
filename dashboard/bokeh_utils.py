from bokeh.plotting import figure, show
from bokeh.embed import components
from bokeh.models import DatetimeTickFormatter


class Plot:
    def __init__(self, x_list, y_list):
        self.x_list = x_list
        self.y_list = y_list
        self.plot = None

    def plot_timeseries(self):
        self.plot_line_graph(
            title="Timeseries",
            x_axis_type="datetime"
        )
        self.plot.xaxis[0].formatter = DatetimeTickFormatter(minsec=':%M:%S')

    def plot_line_graph(self, title=None, x_label=None, y_label=None, x_axis_type=None, y_axis_type=None):
        self.plot = figure(
            title=title,
            x_axis_label=x_label,
            y_axis_label=y_label,
            x_axis_type=x_axis_type,
            y_axis_type=y_axis_type,
            sizing_mode="stretch_width",
            height=360
        )

        self.plot.line(self.x_list, self.y_list)
        self.plot.circle_cross(self.x_list, self.y_list, size=4)

    def get_components(self):
        if self.plot:
            return components(self.plot)
        else:
            return None