import sys

from integrations.ipfs_datasets.loader import import_module_optional


def test_import_module_optional_can_resolve_vendored_llm_router_from_shadowed_repo_layout():
    for module_name in list(sys.modules):
        if module_name == 'ipfs_datasets_py' or module_name.startswith('ipfs_datasets_py.'):
            sys.modules.pop(module_name, None)

    module, error = import_module_optional('ipfs_datasets_py.llm_router')

    assert error is None
    assert module is not None
    assert getattr(module, '__file__', '').endswith('/ipfs_datasets_py/llm_router.py')