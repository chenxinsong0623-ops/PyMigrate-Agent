from pydantic.generics import GenericModel as GM


class DirectBox(GM):
    value: object


import pydantic.generics as pg  # noqa: E402


class ModuleBox(pg.GenericModel):
    value: object


from another_library import GenericModel as OtherGenericModel  # noqa: E402


class OtherBox(OtherGenericModel):
    value: object


class GenericModel:
    pass


class LocalBox(GenericModel):
    value: object


import pydantic.generics as rebound  # noqa: E402, I001


rebound = another_module  # noqa: F811, F821


class ReboundBox(rebound.GenericModel):
    value: object


description = "GenericModel candidate fixture"
