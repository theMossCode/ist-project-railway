import datetime

from bokeh.plotting import figure, show
from bokeh.embed import components
from bokeh.models import DatetimeTickFormatter, ColumnDataSource


class Plot:
    def __init__(self, x_list, y_list):
        self.data_source = dict()
        self.data_source["x_values"] = x_list
        self.data_source["y_values"] = y_list
        self.figure = None

    def plot_timeseries(self, include_line=False):
        self.line_plot(
            title="Timeseries",
            x_axis_type="datetime",
            include_markers=True
        )
        self.figure.xaxis[0].formatter = DatetimeTickFormatter(
            hourmin="%H:%M",
            minsec="%H:%M:%S",
            minutes="%I:%M",
            context=str(self.data_source["x_values"][-1].strftime("%d/%m/%y %I:%M %p")),
            context_which="start"
        )

    def create_figure(self, title=None, x_label=None, y_label=None, x_axis_type="linear", y_axis_type="linear"):
        self.figure = figure(
            title=title,
            x_axis_label=x_label,
            y_axis_label=y_label,
            x_axis_type=x_axis_type,
            y_axis_type=y_axis_type,
            sizing_mode="stretch_width",
            height=360
        )

    def scatter_plot(self, title=None, x_label=None, y_label=None, x_axis_type="linear", y_axis_type="linear"):
        self.create_figure(title, x_label, y_label, x_axis_type, y_axis_type)
        self.figure.circle(x="x_values", y="y_values", source=self.data_source, size=5)

    def line_plot(self, title=None, x_label=None, y_label=None, x_axis_type="linear", y_axis_type="linear",
                  include_markers=False):
        self.create_figure(title, x_label, y_label, x_axis_type, y_axis_type)
        self.figure.line(x="x_values", y="y_values", source=self.data_source)
        if include_markers:
            self.figure.circle(x="x_values", y="y_values", source=self.data_source, fill_color="gray",
                               size=5)

    def get_components(self):
        if self.figure:
            return components(self.figure)
        else:
            return None
