import datetime
import logging
from math import pi
from bokeh.plotting import figure, show
from bokeh.embed import components
from bokeh.models import DatetimeTickFormatter, ColumnDataSource, Arc, Plot, Range1d


class GaugeMixin:
    def value_to_gauge_angle(self, value, max_value):
        ratio = value/max_value
        raw_angle = ratio * pi
        return pi - raw_angle


class BokehPlot(GaugeMixin):
    def __init__(self, x_list=None, y_list=None):
        self.data_source = dict()
        self.data_source["x_values"] = x_list
        self.data_source["y_values"] = y_list
        self.figure = None

    def plot_timeseries(self):
        self.line_plot(
            title="Timeseries",
            x_axis_type="datetime",
        )
        self.figure.xaxis[0].formatter = DatetimeTickFormatter(
            hourmin="%H:%M",
            minsec="%M:%S",
            minutes="%H:%M",
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

    def gauge_plot(self, value, max_value):
        x_range = Range1d(-pi, pi)
        current_angle = self.value_to_gauge_angle(value, max_value)
        self.create_figure(
            x_axis_type=None,
            y_axis_type=None
        )
        self.figure.x_range = Range1d(-100, 100)
        self.figure.y_range = Range1d(-50, 100)
        self.figure.outline_line_color = None
        self.figure.toolbar_location = None
        self.figure.annular_wedge(
            x=0,
            y=0,
            inner_radius=60,
            outer_radius=100,
            start_angle=pi,
            end_angle=0,
            direction="clock",
            fill_color="#E6E6E3",
            line_width=0
        )
        self.figure.annular_wedge(
            x=0,
            y=0,
            inner_radius=60,
            outer_radius=100,
            start_angle=pi,
            end_angle=current_angle,
            direction="clock",
            # fill_color="blue",
        )

        self.figure.text(
            x=0,
            y=0,
            text_align="center",
            text_font_style="bold",
            text_color="black",
            text=[f"{value}/{max_value}"]
        )

    def get_components(self):
        if self.figure:
            return components(self.figure)
        else:
            return None
