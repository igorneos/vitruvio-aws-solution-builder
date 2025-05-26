import os
import boto3
import streamlit as st
import get_code_from_markdown
from botocore.config import Config
from utils import BEDROCK_MODEL_ID
from utils import invoke_bedrock_model_streaming
from utils import retrieve_environment_variables
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
import uuid

AWS_REGION = os.getenv("AWS_REGION")

config = Config(read_timeout=1000, retries=(dict(max_attempts=5)))
s3_client = boto3.client('s3', region_name=AWS_REGION)
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)


# Generate Terraform
@st.fragment
def generate_terraform(terraform_messages):
    terraform_messages = terraform_messages[:]

    # Retain messages and previous insights in the chat section
    if 'terraform_messages' not in st.session_state:
        st.session_state.terraform_messages = []

    # Create the radio button for terraform selection
    if 'terraform_user_select' not in st.session_state:
        st.session_state.terraform_user_select = False  # Initialize the value if it doesn't exist

    left, middle, right = st.columns([4, 0.5, 0.5])

    with left:
        st.markdown(
            "<div style='font-size: 18px'><b>Use the checkbox below to generate Terraform code to deploy the proposed solution as Infrastructure as Code</b></div>",  # noqa
            unsafe_allow_html=True)
        st.divider()
        st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
        select_terraform = st.checkbox(
            "Check this box to generate Terraform code",
            key="terraform"
        )
        # Only update the session state when the checkbox value changes
        if select_terraform != st.session_state.terraform_user_select:
            st.session_state.terraform_user_select = select_terraform
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        if st.session_state.terraform_user_select:
            st.markdown("<div class=stButton gen-style'>", unsafe_allow_html=True)
            if st.button(label="⟳ Retry", key="retry-terraform", type="secondary"):
                st.session_state.terraform_user_select = True  # Probably redundant
            st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.terraform_user_select:
        terraform_prompt = """
            For the given solution, generate Terraform configuration files to automate the deployment of AWS resources.
            Provide the actual source code for all the jobs wherever applicable.
            The Terraform configuration should provision all the resources and the components.
            If Python code is needed, generate a "Hello, World!" code example.
            Use the AWS provider and follow Terraform best practices including:
            - Proper resource naming conventions
            - Use of variables for configurable values
            - Output values for important resource attributes
            - Appropriate resource dependencies
            At the end generate sample commands to deploy the Terraform configuration including:
            - terraform init
            - terraform plan
            - terraform apply
        """  # noqa

        terraform_messages.append({"role": "user", "content": terraform_prompt})

        terraform_response, stop_reason = invoke_bedrock_model_streaming(terraform_messages)
        st.session_state.terraform_messages.append({"role": "assistant", "content": terraform_response})

        terraform_code = get_code_from_markdown.get_code_from_markdown(terraform_response, language="hcl")
        if not terraform_code:
            # Try to extract terraform code blocks
            terraform_code = get_code_from_markdown.get_code_from_markdown(terraform_response, language="terraform")

        with st.container(height=350):
            st.markdown(terraform_response)

        S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")

        st.session_state.interaction.append({"type": "Terraform Configuration", "details": terraform_response})
        store_in_s3(content=terraform_response, content_type='terraform')
        save_conversation(st.session_state['conversation_id'], terraform_prompt, terraform_response)
        collect_feedback(str(uuid.uuid4()), terraform_response, "generate_terraform", BEDROCK_MODEL_ID)

        # Write Terraform configuration to S3 bucket
        if terraform_code:
            object_name = f"{st.session_state['conversation_id']}/main.tf"
            s3_client.put_object(Body=terraform_code[0], Bucket=S3_BUCKET_NAME, Key=object_name)
            
        st.write("To deploy the generated Terraform configuration:")
        st.markdown("""
        1. Download the generated Terraform files
        2. Install Terraform on your local machine if not already installed
        3. Configure AWS credentials (AWS CLI or environment variables)
        4. Run the following commands:
        ```bash
        terraform init
        terraform plan
        terraform apply
        ```
        """)
        
        st.markdown("If you don't have an AWS account, you can create one by clicking [this link](https://signin.aws.amazon.com/signup?request_type=register).")  # noqa
        st.markdown("For Terraform installation instructions, visit [terraform.io](https://www.terraform.io/downloads.html)")  # noqa