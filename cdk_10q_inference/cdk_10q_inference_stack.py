from aws_cdk import Stack, aws_iam as iam
from constructs import Construct

class Cdk10QInferenceStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bedrock_role = iam.Role(
            self, "BedrockInvokeRole",
            assumed_by=iam.AccountPrincipal(self.account),
            description="Allows invoking Claude on Bedrock for 10Q Inference Part 1"
        )

        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:Converse"],
                resources=[
                    f"arn:aws:bedrock:us-east-1:{self.account}:inference-profile/us.anthropic.claude-sonnet-4-5-*"
                ]
            )
        )
