import pydantic as pd  # noqa: I001
from another_library import Field as OtherField
from pydantic import Field
from pydantic import Field as F


one = Field(const=True)
two = F(min_items=1)
three = pd.Field(max_items=3)
four = Field(unique_items=True)
five = F(allow_mutation=False)
six = pd.Field(regex="^[a-z]+$")
seven = Field(final=True)
eight = F(widget="compact")


valid = Field(
    title="Title",
    pattern="^[a-z]+$",
    min_length=1,
    json_schema_extra={"widget": "compact"},
)


other = OtherField(regex="x")
dynamic_options = {"regex": "x"}
dynamic = Field(**dynamic_options)


F = custom_field  # noqa: F821
shadowed = F(regex="x")


pd = another_module  # noqa: F821
shadowed_module = pd.Field(regex="x")


description = "Field keyword candidate fixture"
