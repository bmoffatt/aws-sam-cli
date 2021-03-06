from unittest import TestCase
from unittest.mock import patch, Mock

import botocore.session

from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError
from botocore.stub import Stubber

from samcli.commands.bootstrap.exceptions import ManagedStackError
from samcli.commands.exceptions import UserException, CredentialsError, RegionError
from samcli.lib.bootstrap.bootstrap import manage_stack, _create_or_get_stack, _get_stack_template, SAM_CLI_STACK_NAME


class TestBootstrapManagedStack(TestCase):
    def _stubbed_cf_client(self):
        cf = botocore.session.get_session().create_client("cloudformation")
        return [cf, Stubber(cf)]

    @patch("boto3.Session")
    def test_client_missing_credentials(self, boto_mock):
        session_mock = Mock()
        session_mock.client.side_effect = NoCredentialsError()
        boto_mock.return_value = session_mock
        with self.assertRaises(CredentialsError):
            manage_stack("testprofile", "fake-region")

    @patch("boto3.Session")
    def test_client_missing_region(self, boto_mock):
        session_mock = Mock()
        session_mock.client.side_effect = NoRegionError()
        boto_mock.return_value = session_mock
        with self.assertRaises(RegionError):
            manage_stack("testprofile", "fake-region")

    def test_new_stack(self):
        stub_cf, stubber = self._stubbed_cf_client()
        # first describe_stacks call will fail
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_client_error("describe_stacks", service_error_code="ClientError", expected_params=ds_params)
        # creating change set
        ccs_params = {
            "StackName": SAM_CLI_STACK_NAME,
            "TemplateBody": _get_stack_template(),
            "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
            "ChangeSetType": "CREATE",
            "ChangeSetName": "InitialCreation",
        }
        ccs_resp = {"Id": "id", "StackId": "aws-sam-cli-managed-default"}
        stubber.add_response("create_change_set", ccs_resp, ccs_params)
        # describe change set creation status for waiter
        dcs_params = {"ChangeSetName": "InitialCreation", "StackName": SAM_CLI_STACK_NAME}
        dcs_resp = {"Status": "CREATE_COMPLETE"}
        stubber.add_response("describe_change_set", dcs_resp, dcs_params)
        # executing change set
        ecs_params = {"ChangeSetName": "InitialCreation", "StackName": SAM_CLI_STACK_NAME}
        ecs_resp = {}
        stubber.add_response("execute_change_set", ecs_resp, ecs_params)
        # two describe_stacks calls will succeed - one for waiter, one direct
        post_create_ds_resp = {
            "Stacks": [
                {
                    "StackName": SAM_CLI_STACK_NAME,
                    "CreationTime": "2019-11-13",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
                    "Outputs": [{"OutputKey": "SourceBucket", "OutputValue": "generated-src-bucket"}],
                }
            ]
        }
        stubber.add_response("describe_stacks", post_create_ds_resp, ds_params)
        stubber.add_response("describe_stacks", post_create_ds_resp, ds_params)
        stubber.activate()
        _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_stack_exists(self):
        stub_cf, stubber = self._stubbed_cf_client()
        ds_resp = {
            "Stacks": [
                {
                    "StackName": SAM_CLI_STACK_NAME,
                    "CreationTime": "2019-11-13",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
                    "Outputs": [{"OutputKey": "SourceBucket", "OutputValue": "generated-src-bucket"}],
                }
            ]
        }
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_response("describe_stacks", ds_resp, ds_params)
        stubber.activate()
        _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_stack_missing_bucket(self):
        stub_cf, stubber = self._stubbed_cf_client()
        ds_resp = {
            "Stacks": [
                {
                    "StackName": SAM_CLI_STACK_NAME,
                    "CreationTime": "2019-11-13",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
                    "Outputs": [],
                }
            ]
        }
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_response("describe_stacks", ds_resp, ds_params)
        stubber.activate()
        with self.assertRaises(UserException):
            _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_stack_missing_tag(self):
        stub_cf, stubber = self._stubbed_cf_client()
        ds_resp = {
            "Stacks": [
                {
                    "StackName": SAM_CLI_STACK_NAME,
                    "CreationTime": "2019-11-13",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [],
                    "Outputs": [{"OutputKey": "SourceBucket", "OutputValue": "generated-src-bucket"}],
                }
            ]
        }
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_response("describe_stacks", ds_resp, ds_params)
        stubber.activate()
        with self.assertRaises(UserException):
            _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_stack_wrong_tag(self):
        stub_cf, stubber = self._stubbed_cf_client()
        ds_resp = {
            "Stacks": [
                {
                    "StackName": SAM_CLI_STACK_NAME,
                    "CreationTime": "2019-11-13",
                    "StackStatus": "CREATE_COMPLETE",
                    "Tags": [{"Key": "ManagedStackSource", "Value": "WHY WOULD YOU EVEN DO THIS"}],
                    "Outputs": [{"OutputKey": "SourceBucket", "OutputValue": "generated-src-bucket"}],
                }
            ]
        }
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_response("describe_stacks", ds_resp, ds_params)
        stubber.activate()
        with self.assertRaises(UserException):
            _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_change_set_creation_fails(self):
        stub_cf, stubber = self._stubbed_cf_client()
        # first describe_stacks call will fail
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_client_error("describe_stacks", service_error_code="ClientError", expected_params=ds_params)
        # creating change set - fails
        ccs_params = {
            "StackName": SAM_CLI_STACK_NAME,
            "TemplateBody": _get_stack_template(),
            "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
            "ChangeSetType": "CREATE",
            "ChangeSetName": "InitialCreation",
        }
        stubber.add_client_error("create_change_set", service_error_code="ClientError", expected_params=ccs_params)
        stubber.activate()
        with self.assertRaises(ManagedStackError):
            _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()

    def test_change_set_execution_fails(self):
        stub_cf, stubber = self._stubbed_cf_client()
        # first describe_stacks call will fail
        ds_params = {"StackName": SAM_CLI_STACK_NAME}
        stubber.add_client_error("describe_stacks", service_error_code="ClientError", expected_params=ds_params)
        # creating change set
        ccs_params = {
            "StackName": SAM_CLI_STACK_NAME,
            "TemplateBody": _get_stack_template(),
            "Tags": [{"Key": "ManagedStackSource", "Value": "AwsSamCli"}],
            "ChangeSetType": "CREATE",
            "ChangeSetName": "InitialCreation",
        }
        ccs_resp = {"Id": "id", "StackId": "aws-sam-cli-managed-default"}
        stubber.add_response("create_change_set", ccs_resp, ccs_params)
        # describe change set creation status for waiter
        dcs_params = {"ChangeSetName": "InitialCreation", "StackName": SAM_CLI_STACK_NAME}
        dcs_resp = {"Status": "CREATE_COMPLETE"}
        stubber.add_response("describe_change_set", dcs_resp, dcs_params)
        # executing change set - fails
        ecs_params = {"ChangeSetName": "InitialCreation", "StackName": SAM_CLI_STACK_NAME}
        stubber.add_client_error(
            "execute_change_set", service_error_code="InsufficientCapabilities", expected_params=ecs_params
        )
        stubber.activate()
        with self.assertRaises(ManagedStackError):
            _create_or_get_stack(stub_cf)
        stubber.assert_no_pending_responses()
        stubber.deactivate()
