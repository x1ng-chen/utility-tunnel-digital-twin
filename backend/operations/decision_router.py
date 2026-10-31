"""Bounded local AnyJev routing. This module never executes a tool or action.

The sidecar is optional and closed by default. Its distributions are model
outputs, not calibrated incident/safety probabilities. Failures are observable
fallbacks; they never enable another provider or a hardware command.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings


MODEL = 'morriszjm/Tacit-1.7B'
MODEL_REVISION = '1cb46fff0ffeefc4965455185074be5c62adccf7'
ANYJEV_COMMIT = '35311c58955716cb8955ce1368a665988bc63735'
AUTHORITY = 'READ_ONLY_ROUTING'
MAX_BODY_BYTES = 65536
MAX_RESPONSE_BYTES = 32768
OPTION_ID = re.compile(r'[a-z][a-z0-9_]{0,47}\Z')


def _setting(name, default=None):
    return getattr(settings, name, os.environ.get(name, default))


def enabled():
    """A configuration signal, not a health or successful-inference assertion."""
    value = _setting('ANYJEV_ENABLED', False)
    return value is True or isinstance(value, str) and value.lower().strip() in {'1', 'true', 'yes'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _fallback(reason, *, attempted=False, started=None, request_id=None, **extra):
    return {
        'provider': 'LOCAL_ANYJEV', 'model': MODEL, 'modelRevision': MODEL_REVISION,
        'anyjevCommit': ANYJEV_COMMIT, 'authority': AUTHORITY,
        'status': 'fallback', 'selectedOption': None, 'probabilities': {},
        'logProbabilityGap': None, 'fallbackReason': reason, 'attempted': attempted,
        'requestId': request_id, 'usage': None, 'cost': None,
        'runtime': {'elapsedMs': round((time.monotonic() - started) * 1000, 3) if started else 0},
        'probabilitiesCalibratedForProject': False, **extra,
    }


def _options(options):
    if not isinstance(options, list) or not 2 <= len(options) <= 8:
        raise ValueError('invalid_options')
    result, seen = [], set()
    for option in options:
        if not isinstance(option, dict) or set(option) - {'id', 'label', 'description'}:
            raise ValueError('invalid_options')
        code, label, description = option.get('id'), option.get('label'), option.get('description', '')
        if not isinstance(code, str) or not OPTION_ID.fullmatch(code) or code in seen:
            raise ValueError('invalid_options')
        if not isinstance(label, str) or not 1 <= len(label) <= 100:
            raise ValueError('invalid_options')
        if not isinstance(description, str) or len(description) > 400:
            raise ValueError('invalid_options')
        seen.add(code)
        result.append({'id': code, 'label': label, 'description': description})
    if 'uncertain' not in seen:
        raise ValueError('missing_uncertain_option')
    return result


def _endpoint():
    value = _setting('ANYJEV_URL', 'http://127.0.0.1:8110')
    if not isinstance(value, str):
        raise ValueError('invalid_configuration')
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1'}
            or parsed.username or parsed.password or parsed.path not in {'', '/'}
            or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError('invalid_configuration')
    return value.rstrip('/') + '/v1/decide'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the local service token to a redirect target.


def _distribution(result, option_ids):
    probabilities = result.get('probabilities')
    if not isinstance(probabilities, dict) or set(probabilities) != option_ids:
        raise ValueError('invalid_distribution')
    for value in probabilities.values():
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('invalid_distribution')
    if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0, abs_tol=0.0001):
        raise ValueError('invalid_distribution')
    ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    best, second = ordered[0][1], ordered[1][1]
    if best <= 0:
        raise ValueError('invalid_distribution')
    gap = math.log(best) - math.log(second) if second > 0 else None
    selected = result.get('selectedOption')
    if selected not in option_ids or probabilities[selected] != best:
        raise ValueError('invalid_selection')
    return probabilities, selected, gap


def route_decision(state, options, timeout=5.0):
    """Select one closed-set *read-only* check or return a structured fallback.

    ``attempted`` means an HTTP decision request was attempted. Callers must count
    those attempts, including failures, against the shared model-call deadline.
    Disabled/configuration/input rejections perform no inference and set it false.
    """
    started = time.monotonic()
    request_id = str(uuid.uuid4())
    if not enabled():
        return _fallback('not_enabled', started=started, request_id=request_id)
    try:
        if not isinstance(state, dict):
            raise ValueError('invalid_state')
        options = _options(options)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('deadline_exhausted')
        endpoint = _endpoint()
        token = _setting('ANYJEV_TOKEN', '')
        if not isinstance(token, str) or len(token) < 32 or '\r' in token or '\n' in token:
            raise ValueError('missing_service_token')
        request_payload = {'requestId': request_id, 'state': state, 'options': options}
        payload = canonical(request_payload).encode('utf-8')
        if len(payload) > MAX_BODY_BYTES:
            raise ValueError('input_too_large')
        input_hash, options_hash = _hash(state), _hash(options)
    except (ValueError, TypeError, RecursionError, OverflowError):
        # Do not expose arbitrary state, tokens, or parser exception text.
        return _fallback('invalid_input_or_configuration', started=started, request_id=request_id)

    req = Request(endpoint, data=payload, headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
    }, method='POST')
    try:
        # Environment proxy settings must not take local evidence off the host.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(req, timeout=min(float(timeout), 5.0)) as response:
            if response.status != 200:
                raise ValueError('invalid_response')
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError('invalid_response')
        result = json.loads(body.decode('utf-8'))
        if not isinstance(result, dict):
            raise ValueError('invalid_response')
        if (result.get('requestId') != request_id or result.get('inputHash') != input_hash
                or result.get('optionsHash') != options_hash or result.get('model') != MODEL
                or result.get('modelRevision') != MODEL_REVISION
                or result.get('anyjevCommit') != ANYJEV_COMMIT
                or result.get('authority') != AUTHORITY
                or result.get('executionSource') != 'LOCAL_MODEL'):
            raise ValueError('response_binding_mismatch')
        if result.get('status') not in {'selected', 'fallback'}:
            raise ValueError('invalid_response')
        if result.get('status') == 'fallback' and result.get('fallbackReason') not in {'low_margin', 'uncertain'}:
            allowed = {'token_limit', 'uncertain', 'low_margin', 'busy', 'model_unavailable', 'inference_failed'}
            reason = result.get('fallbackReason')
            return _fallback(reason if reason in allowed else 'model_unavailable', attempted=True,
                             started=started, request_id=request_id,
                             inputHash=input_hash, optionsHash=options_hash)
        distribution_input = result
        if result.get('status') == 'fallback':
            probabilities = result.get('probabilities')
            if not isinstance(probabilities, dict) or not probabilities:
                raise ValueError('invalid_distribution')
            distribution_input = {**result, 'selectedOption': max(probabilities, key=probabilities.get)}
        probabilities, selected, gap = _distribution(distribution_input, {option['id'] for option in options})
        normalized = {
            'provider': 'LOCAL_ANYJEV', 'model': MODEL, 'modelRevision': MODEL_REVISION,
            'anyjevCommit': ANYJEV_COMMIT, 'authority': AUTHORITY, 'status': 'selected',
            'selectedOption': selected, 'probabilities': probabilities,
            'logProbabilityGap': gap, 'fallbackReason': None, 'attempted': True,
            'requestId': request_id, 'inputHash': input_hash, 'optionsHash': options_hash,
            'runtime': {'elapsedMs': round((time.monotonic() - started) * 1000, 3)},
            'usage': None, 'cost': None, 'probabilitiesCalibratedForProject': False,
        }
        runtime=result.get('runtime',{})
        policy=result.get('routerPolicyVersion')
        if isinstance(policy,str) and len(policy)<=100: normalized['routerPolicyVersion']=policy
        if isinstance(runtime,dict):
            for key in ('inferenceMs','peakAllocatedMiB','peakReservedMiB'):
                value=runtime.get(key)
                if type(value) in (int,float) and math.isfinite(value) and value>=0:
                    normalized['runtime'][key]=value
        usage = result.get('usage')
        if isinstance(usage, dict):
            values = [usage.get(key) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')]
            if all(type(value) is int and 0 <= value <= 2048 for value in values) and values[1] == 0 and values[2] == values[0]:
                normalized['usage'] = {key: usage[key] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                normalized['usage']['source'] = 'LOCAL_TOKENIZER_MEASUREMENT'
        if selected == 'uncertain':
            normalized.update(status='fallback', selectedOption=None, fallbackReason='uncertain')
        elif gap is not None and gap < 0.5:
            normalized.update(status='fallback', selectedOption=None, fallbackReason='low_margin')
        if result.get('status') == 'fallback' and normalized['fallbackReason'] != result.get('fallbackReason'):
            raise ValueError('invalid_response')
        return normalized
    except (TimeoutError, socket.timeout):
        reason = 'timeout'
    except HTTPError as exc:
        reason = 'busy' if exc.code in {429, 503} else 'http_error'
    except URLError:
        reason = 'service_unavailable'
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        reason = 'invalid_response'
    except OSError:
        reason = 'service_unavailable'
    return _fallback(reason, attempted=True, started=started, request_id=request_id,
                     inputHash=input_hash, optionsHash=options_hash)
