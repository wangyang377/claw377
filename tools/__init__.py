from . import bash, edit_file, read_file, task, web_fetch, web_search, write_file

_MODULES = [bash, read_file, write_file, edit_file, task, web_fetch, web_search]


def _tool_name(module) -> str:
    return module.TOOL_SCHEMA["function"]["name"]


TOOLS = [module.TOOL_SCHEMA for module in _MODULES]
TOOL_HANDLERS = {_tool_name(module): module.run for module in _MODULES}
