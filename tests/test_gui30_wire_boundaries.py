"""Transport preserves actual bytes and refuses bounded malformed packets."""
from copy import deepcopy
import base64
import hashlib
import json
import lzma
from types import SimpleNamespace
import pytest
from applications.legal_analysis_api import (LegalAnalysisError, _definition_inputs,
    definition_inputs_wire, definition_wire, bind_case_definition_correspondence)
from tests.test_cimp_gui_30 import _bundle, _populations, LEGAL_SOURCE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
TAG = '$complaint_definition_inputs'
BYTE_TAG = '$complaint_definition_bytes'


def _packet(raw, **changes):
    fields = {'version':1,'encoding':'xz-json-base64','byte_length':len(raw),
        'sha256':hashlib.sha256(raw).hexdigest(), 'base64':base64.b64encode(lzma.compress(raw)).decode()}
    fields.update(changes)
    return {TAG:fields}


def test_lossless_wire_preserves_actual_owner_byte_and_receipt_identities():
    inputs = _bundle()
    packet = definition_inputs_wire(inputs)
    assert len(json.dumps(packet).encode()) <= 256 * 1024
    decoded = _definition_inputs(packet)
    plain = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}),
        {'source_text':LEGAL_SOURCE,'request_id':'wire-identity','declared_populations':_populations(), **inputs})
    transported = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}),
        {'source_text':LEGAL_SOURCE,'request_id':'wire-identity','declared_populations':_populations(), **decoded})
    assert plain['status'] == transported['status'] == 'bound'
    assert plain['source_text_sha256'] == transported['source_text_sha256']
    assert plain['owners'] == transported['owners']
    assert plain['proof'] is False and transported['authorizes_law'] is False


@pytest.mark.parametrize('kind', ['checksum','length','truncated','multistream','trailing','unknown_version',
    'mixed_tag','old_encoding','noncanonical_base64','noncanonical_json','duplicate_keys','deep','nodes',
    'zip_bomb','expanded_limit','decoded_bytes','mixed_byte_tag','byte_version','file_tag'])
def test_bounded_packets_cannot_bypass_exact_transport_contract(kind):
    packet = _packet(b'{}')
    fields = packet[TAG]
    if kind == 'checksum': fields['sha256'] = '0' * 64
    elif kind == 'length': fields['byte_length'] = 1
    elif kind == 'truncated': fields['base64'] = base64.b64encode(lzma.compress(b'{}')[:-4]).decode()
    elif kind == 'multistream': fields['base64'] = base64.b64encode(lzma.compress(b'{}') + lzma.compress(b'{}')).decode()
    elif kind == 'trailing': fields['base64'] = base64.b64encode(lzma.compress(b'{}') + b'trailer').decode()
    elif kind == 'unknown_version': fields['version'] = True
    elif kind == 'mixed_tag': packet['other'] = {}
    elif kind == 'old_encoding': fields['encoding'] = 'zlib-json-base64'
    elif kind == 'noncanonical_base64': fields['base64'] += '\n'
    elif kind == 'noncanonical_json': packet = _packet(b'{ "x": 1 }')
    elif kind == 'duplicate_keys': packet = _packet(b'{"x":1,"x":1}')
    elif kind == 'deep': packet = _packet(b'[' * 34 + b'0' + b']' * 34)
    elif kind == 'nodes': packet = _packet(json.dumps([0] * 100001, separators=(',',':')).encode())
    elif kind == 'zip_bomb': packet = _packet(b'x' * (9 * 1024 * 1024), byte_length=1)
    elif kind == 'expanded_limit': fields['byte_length'] = 8 * 1024 * 1024 + 1
    else:
        value = {BYTE_TAG:{'version':1,'base64':'eA=='}}
        if kind == 'decoded_bytes': value[BYTE_TAG]['base64'] = base64.b64encode(b'x' * (2 * 1024 * 1024 + 1)).decode()
        elif kind == 'mixed_byte_tag': value['other'] = 'ignored'
        elif kind == 'byte_version': value[BYTE_TAG]['version'] = True
        elif kind == 'file_tag': value[BYTE_TAG] = {'version':1,'file':'/synthetic-not-read'}
        packet = _packet(json.dumps(value, sort_keys=True, separators=(',',':')).encode())
    with pytest.raises(LegalAnalysisError) as denied:
        _definition_inputs(packet)
    assert denied.value.code in {'legal_analysis_field','legal_analysis_bounds'}
