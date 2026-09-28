from django.test import SimpleTestCase

from .command_dispatch import matching_command_ack


class CommandAckValidationTests(SimpleTestCase):
    def test_accepts_protocol_acknowledgements_for_the_published_command(self):
        for status in ('accepted', 'rejected', 'duplicate', 'expired'):
            ack = {'schema': 'ut.command.ack.v1', 'cmdId': 'platform-123', 'status': status, 'reason': 'test'}
            self.assertEqual(matching_command_ack(ack, 'platform-123'), ack)

    def test_ignores_unrelated_or_malformed_frames(self):
        valid = {'schema': 'ut.command.ack.v1', 'cmdId': 'platform-123', 'status': 'accepted', 'reason': 'test'}
        for frame in (
            None,
            [],
            {**valid, 'schema': 'ut.command.v1'},
            {**valid, 'cmdId': 'platform-other'},
            {**valid, 'status': 'unknown'},
            {**valid, 'status': []},
            {**valid, 'reason': None},
        ):
            self.assertIsNone(matching_command_ack(frame, 'platform-123'))
