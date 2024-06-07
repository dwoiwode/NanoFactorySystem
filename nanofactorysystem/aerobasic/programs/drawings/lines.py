import math
from abc import ABC
from typing import Optional, Literal

import numpy as np

from nanofactorysystem.aerobasic import GalvoLaserOverrideMode, SingleAxis
from nanofactorysystem.aerobasic.programs.drawings import DrawableAeroBasicProgram, DrawableObject
from nanofactorysystem.devices.coordinate_system import CoordinateSystem, Coordinate, Point3D, Point2D


class SingleLine(DrawableObject):
    def __init__(
            self,
            start: Coordinate,
            end: Coordinate,
            *,
            F: Optional[float] = None,
            E: Optional[float] = None,
    ):
        super().__init__()
        self.start = start
        self.end = end
        self.F = F
        self.E = E

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)

        program.LINEAR(*self.start, F=self.F, E=self.E)
        program.GALVO_LASER_OVERRIDE(mode=GalvoLaserOverrideMode.ON)
        program.LINEAR(*self.end, F=self.F, E=self.E)
        program.GALVO_LASER_OVERRIDE(mode=GalvoLaserOverrideMode.OFF)
        return program


class _Lines(DrawableObject, ABC):
    line_axis: SingleAxis

    def __init__(
            self,
            lines: list[tuple[float, float]],
            secondary_position: dict[str, float],
            *,
            velocity: float,
            acceleration: float
    ):
        super().__init__()
        self._validate_lines(lines)
        self.lines = lines
        self.secondary_position = secondary_position
        self.velocity = velocity
        self.acceleration = acceleration

    @staticmethod
    def _direction(line_segment) -> Literal[1, -1]:
        return np.sign(line_segment[1] - line_segment[0])

    @staticmethod
    def _validate_lines(lines):
        """ Check whether lines are monoton ascending """
        direction = _Lines._direction(lines[0])
        for i, line in enumerate(lines[1:], start=1):
            if not _Lines._direction(line) == direction:
                raise ValueError(
                    f"Direction mismatch. "
                    f"Line {i} does not match with direction of line 0 ({lines[0]} vs {lines[i]}"
                )

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)

        # Go to start for acceleration
        acceleration_distance = (self.velocity ** 2) / (2 * self.acceleration)
        start_value = self.lines[0][0] - self._direction(self.lines[0]) * acceleration_distance
        start_position = {self.line_axis.parameter_name: start_value, "F": self.velocity}
        start_position.update(self.secondary_position)
        program.LINEAR(**start_position)

        # Draw lines
        for line_start, line_end in self.lines:
            program.LINEAR(**{self.line_axis.parameter_name: line_start, "F": self.velocity})
            program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.ON)
            program.LINEAR(**{self.line_axis.parameter_name: line_end, "F": self.velocity})
            program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.OFF)

        # Go to end to decelerate
        end_value = self.lines[-1][1] + self._direction(self.lines[0]) * acceleration_distance
        end_position = {self.line_axis.parameter_name: end_value, "F": self.velocity}
        end_position.update(self.secondary_position)
        program.LINEAR(**end_position)

        return program


class XLines(_Lines):
    line_axis = SingleAxis.X

    def __init__(
            self,
            y: float,
            z: float,
            lines: list[tuple[float, float]],
            *,
            velocity: float,
            acceleration: float
    ):
        super().__init__(lines, {"Y": y, "Z": z}, velocity=velocity, acceleration=acceleration)
        self.y = y
        self.z = z

    def center_point(self) -> Point2D:
        return Point3D((self.lines[0][0] + self.lines[-1][1]) / 2, self.y, self.z)


class YLines(_Lines):
    line_axis = SingleAxis.Y

    def __init__(
            self,
            x: float,
            z: float,
            lines: list[tuple[float, float]],
            *,
            velocity: float,
            acceleration: float
    ):
        super().__init__(lines, {"X": x, "Z": z}, velocity=velocity, acceleration=acceleration)
        self.x = x
        self.z = z

    def center_point(self) -> Point2D:
        return Point3D(self.x, (self.lines[0][0] + self.lines[-1][1]) / 2, self.z)


class PolyLine(DrawableObject):

    def __init__(
            self,
            line: list[Coordinate],
            *,
            F: Optional[float] = None,
            E: Optional[float] = None,
    ):
        super().__init__()
        self.line = line
        self.F = F
        self.E = E

    @property
    def center_point(self) -> Point2D:
        values = {k: [] for k in self.line[0]}
        for coordinate in self.line:
            for k, v in coordinate.items():
                values[k].append(v)
        min_coord = {k: np.min(v) for k, v in values}
        max_coord = {k: np.max(v) for k, v in values}

        center = {k: (min_coord[k] + max_coord[k]) / 2 for k in min_coord}
        try:
            return Point3D(**center)
        except:
            return Point2D(**center)

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)

        program.LINEAR(**self.line[0], F=self.F, E=self.E)
        program.GALVO_LASER_OVERRIDE(mode=GalvoLaserOverrideMode.ON)
        for point in self.line[1:]:
            program.LINEAR(**point, F=self.F, E=self.E)
        program.GALVO_LASER_OVERRIDE(mode=GalvoLaserOverrideMode.OFF)
        return program


class PolyLines(DrawableObject):

    def __init__(
            self,
            lines: list[list[Coordinate]],
            *,
            F: Optional[float] = None,
            E: Optional[float] = None,
    ):
        super().__init__()
        self.lines = lines
        self.F = F
        self.E = E

    @property
    def center_point(self) -> Point2D:
        values = {k: [] for k in self.lines[0][0]}
        for line in self.lines:
            for coordinate in line:
                for k, v in coordinate.items():
                    values[k].append(v)
        min_coord = {k: np.min(v) for k, v in values}
        max_coord = {k: np.max(v) for k, v in values}

        center = {k: (min_coord[k] + max_coord[k]) / 2 for k in min_coord}
        try:
            return Point3D(**center)
        except:
            return Point2D(**center)

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)
        for i, line in enumerate(self.lines):
            # Start
            program.comment(f"\n[Polyline] - Draw line {i}:")
            poly_line = PolyLine(line, F=self.F, E=self.E)
            program.add_programm(poly_line.draw_on(coordinate_system))

        return program


class Corner(DrawableObject):
    def __init__(
            self,
            corner_center: Point2D | Point3D,
            length: float,
            width: float,
            height: float,
            hatch_size: float = 0.5,
            layer_height: float = 0.75,
            rotation_degree: float = 0,
            *,
            F: Optional[float] = None,
            E: Optional[float] = None,
    ):
        """
                     Length
        \\-----------------   |
        |\\----------------   |
        ||X----------------  Width
        |||\\--------------   |
        ||||\\-------------   |
        |||||
        |||||
        |||||

        :param corner_center: Marked with X
        :param length: Length of corner
        :param width: Width of corner
        :param hatch_size: Distance between lines
        :param rotation_degree: Rotation of corner in degree
        :param F: Velocity used for Linear commands
        :param E: Velocity used for Linear commands
        """
        super().__init__()
        self.corner_center = corner_center
        self.width = width
        self.hatch_size = hatch_size
        self.length = length
        self.rotation_degree = rotation_degree
        self.rotation_rad = rotation_degree / 180 * math.pi
        self.height = height
        self.layer_height = layer_height
        self.F = F
        self.E = E

    @property
    def center_point(self) -> Point2D:
        center_offset = (self.length - self.width) / 2
        return self.corner_center + Point2D(center_offset, center_offset).rotate2D(self.rotation_rad)

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)
        n = round(self.width / self.hatch_size) + 1
        hatch_corrected = self.width / (n - 1)

        change_start = False
        for z in np.arange(0, self.height, self.layer_height):
            poly_lines = self.single_layer(
                self.corner_center + Point3D(0, 0, z),
                self.length,
                self.width,
                n,
                hatch_corrected,
                change_start=change_start,
                E=self.E,
                F=self.F,
                rotation_rad=self.rotation_rad
            )
            change_start = not change_start
            program.add_programm(poly_lines.draw_on(coordinate_system))

        return program

    def single_layer(
            self,
            corner_center: Point2D | Point3D,
            length: float,
            width: float,
            n: int,
            hatch: float,
            *,
            change_start: bool = False,
            E: Optional[float] = None,
            F: Optional[float] = None,
            rotation_rad: float = 0
    ) -> PolyLines:
        lines = []
        for i in range(n):
            center_diagonal = -(i - n / 2) * hatch
            offset = length - width / 2

            center_diagonal = Point2D(center_diagonal, center_diagonal)
            offset = Point2D(offset, offset)

            p1 = corner_center + Point2D(X=offset.X, Y=center_diagonal.Y).rotate2D(rotation_rad)
            p2 = corner_center + Point2D(X=center_diagonal.X, Y=center_diagonal.Y).rotate2D(rotation_rad)
            p3 = corner_center + Point2D(X=center_diagonal.X, Y=offset.Y).rotate2D(rotation_rad)

            if (i + change_start) % 2 == 0:
                lines.append([p1.as_dict(), p2.as_dict(), p3.as_dict()])
            else:
                lines.append([p3.as_dict(), p2.as_dict(), p1.as_dict()])
        return PolyLines(lines, F=F, E=E)


class CornerRectangle(DrawableObject):
    def __init__(
            self,
            center: Point2D | Point3D,
            rectangle_width: float,
            rectangle_height: float,
            corner_length: float,
            corner_width: float,
            height: float,
            layer_height: float = 0.75,
            hatch_size: float = 0.5,
            # rotation_degree: float,
            *,
            F: Optional[float] = None,
            E: Optional[float] = None,
    ):
        super().__init__()
        self.center = center
        self.rectangle_width = rectangle_width
        self.rectangle_height = rectangle_height
        self.corner_length = corner_length
        self.corner_width = corner_width
        self.height = height
        self.layer_height = layer_height
        self.hatch_size = hatch_size
        self.F = F
        self.E = E

        self.tl_corner = Corner(
            center + Point2D(-rectangle_width / 2, -rectangle_height / 2),
            length=corner_length,
            width=corner_width,
            height=height,
            layer_height=layer_height,
            hatch_size=hatch_size,
            rotation_degree=0,
            E=E,
            F=F,
        )
        self.tr_corner = Corner(
            center + Point2D(rectangle_width / 2, -rectangle_height / 2),
            length=corner_length,
            width=corner_width,
            height=height,
            layer_height=layer_height,
            hatch_size=hatch_size,
            rotation_degree=90,
            E=E,
            F=F,
        )
        self.bl_corner = Corner(
            center + Point2D(-rectangle_width / 2, rectangle_height / 2),
            length=corner_length,
            width=corner_width,
            height=height,
            layer_height=layer_height,
            hatch_size=hatch_size,
            rotation_degree=270,
            E=E,
            F=F,
        )
        self.br_corner = Corner(
            center + Point2D(rectangle_width / 2, rectangle_height / 2),
            length=corner_length,
            width=corner_width,
            height=height,
            layer_height=layer_height,
            hatch_size=hatch_size,
            rotation_degree=180,
            E=E,
            F=F,
        )

    @property
    def center_point(self) -> Point2D:
        return self.center

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)

        program.comment("\nDrawing Top Left corner")
        program.add_programm(self.tl_corner.draw_on(coordinate_system))
        program.comment("\nDrawing Top Right corner")
        program.add_programm(self.tr_corner.draw_on(coordinate_system))
        program.comment("\nDrawing Bottom Right corner")
        program.add_programm(self.br_corner.draw_on(coordinate_system))
        program.comment("\nDrawing Bottom Left corner")
        program.add_programm(self.bl_corner.draw_on(coordinate_system))
        return program


class Rectangle3D(DrawableObject):
    def __init__(
            self,
            bottom_left: Point2D | Point3D,
            width: float,
            length: float,
            structure_height: float,
            *,
            hatch_size: float,
            layer_height: float,
            velocity: Optional[float] = None,
    ):
        super().__init__()
        self.bottom_left = bottom_left
        self.width = width
        self.length = length

        self.height = structure_height
        self.layer_height = layer_height
        self.hatch_size = hatch_size
        self.velocity = velocity

    @property
    def center_point(self) -> Point2D:
        return self.bottom_left + Point2D(self.width / 2, self.height / 2)

    def calc_points_layer(
            self,
            slicing_direction: int,
            *,
            starting_point: Point2D | Point3D = None
    ) -> list:
        """
        Converts a Rectangle (defined by starting Point and width/ height) to a list of points.

        slicing direction 0 = horizontal
        slicing direction 1 = vertical
        """
        point_list = []  # for saving the points - startpoint and endpoint in each row of the list
        if slicing_direction == 0:  # horizontal - length = a
            a = self.length
        elif slicing_direction == 1:  # vertical - width = a
            a = self.width
        else:
            raise NotImplementedError(
                f"No Implementation for slicing direction {slicing_direction}. Please use slicing direction 0 for "
                f"horizontal slicing and slicing direction 1 for vertical slicing.")

        N = np.ceil(a / self.hatch_size)  # number of hatching lines
        hatch_size_opt = a / N  # optimised hatch size
        i = 0  # running variable

        for i in range(N):
            if not point_list:
                if starting_point is None or starting_point == 0:
                    point_start = self.bottom_left + i * hatch_size_opt
                else:
                    point_start = starting_point + i * hatch_size_opt
            else:
                point_start = point_list[-1][1] + i * hatch_size_opt
            point_end = point_start + a * (-1) ** (i % 2)

            point_list.append((point_start, point_end))
        return point_list

    # ToDo Kontrollieren der Punkte, damit die auch dreidimensional immer sind.
    # ToDO dazu auf jeden fall kontrollieren, dass die hatching size und die layer height usw auch vektoriell addiert werden
    def slicing_layers(self) -> list:
        N = np.ceil(self.height / self.layer_height)  # number of layers for slicing
        layer_height_opt = self.height / N  # optimised layer height
        i = 0  # running variable
        a = None  # starting point for slicing layer
        points_structure = []  # list of all points layer by layer

        for i in range(N):
            layer = self.calc_points_layer(i % 2, starting_point=a)
            points_structure.append(layer)
            a = points_structure[-1][-1][1] + i * self.layer_height

        return points_structure

    # def adding_acceleration(self, structure_points: list):
    #  all_points = []
    # for layer in structure_points:
    #    for line in layer:
    #       # direction vector with starting and endpoint
    #      # designing length of acceleration part
    #     # adding acceleration points before and after each line
    #    pass
    #      # saving the "new" point structure
    #     pass
    # return all_points

    def adding_acceleration(self, structure_points: list):
        all_points = []
        # ToDo: change description of this method
        for layer in structure_points:
            new_layer = []
            for line in layer:
                # Assuming each line has two points: [start_point, end_point]
                start_point = np.array(line[0])
                end_point = np.array(line[1])

                # Calculate the direction vector
                direction_vector = end_point - start_point

                # Normalize the direction vector
                norm_direction_vector = direction_vector / np.linalg.norm(direction_vector)

                # Calculate the length of the acceleration part (assume a specific length, e.g., 1 unit)
                # TODO: calculate length in dependence on acceleration
                length = 1.0

                # Calculate the new points
                new_start_point = start_point - norm_direction_vector * length
                new_end_point = end_point + norm_direction_vector * length

                # Add the new points to the new layer
                new_layer.append(
                    [new_start_point.tolist(), start_point.tolist(), end_point.tolist(), new_end_point.tolist()])

            # Save the "new" point structure
            all_points.append(new_layer)

        return all_points

    def points_to_cmds(self,
                       program: DrawableAeroBasicProgram,
                       structure_points: list
                       ):
        for layer in structure_points:
            for line in layer:
                point_start_accel = line[0]
                point_start_laser = line[1]
                point_end_laser = line[2]
                point_end_accel = line[3]

                program.LINEAR(X=point_start_accel[0], Y=point_start_accel[1], Z=point_start_accel[2])
                program.LINEAR(X=point_start_laser[0], Y=point_start_laser[1], Z=point_start_laser[2])
                program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.ON)
                program.LINEAR(X=point_end_laser[0], Y=point_end_laser[1], Z=point_end_laser[2])
                program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.OFF)
                program.LINEAR(X=point_end_accel[0], Y=point_end_accel[1], Z=point_end_accel[2])
        return program

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        raise NotImplementedError("TODO: Implement further")
        program = DrawableAeroBasicProgram(coordinate_system)
        list_of_points = self.single_layer()
        list_of_points = self.adding_acceleration(list_of_points)

        program = self.points_to_cmds(program, list_of_points)
        return program


class VerticalLine(DrawableObject):
    def __init__(self, position: Point2D, z_min: float, z_max: float, *, F: Optional[float] = None):
        super().__init__()
        self.position = position
        self.z_min = z_min
        self.z_max = z_max
        self.F = F

    @property
    def center_point(self) -> Point2D:
        return self.position

    def draw_on(self, coordinate_system: CoordinateSystem) -> DrawableAeroBasicProgram:
        program = DrawableAeroBasicProgram(coordinate_system)
        point = self.position.as_dict()
        point["Z"] = self.z_min
        program.LINEAR(**point, F=self.F)
        program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.ON)
        point["Z"] = self.z_max
        program.LINEAR(**point, F=self.F)
        program.GALVO_LASER_OVERRIDE(GalvoLaserOverrideMode.OFF)
        return program