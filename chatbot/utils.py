import streamlit as st
import uuid
import boto3
import os
import json
from botocore.config import Config
from botocore.exceptions import ClientError
from defusedxml.ElementTree import fromstring
from defusedxml.ElementTree import tostring
import datetime
import time
import tempfile
import glob
import zipfile
import shutil
from pathlib import Path
import base64

AWS_REGION = os.getenv("AWS_REGION")
config = Config(read_timeout=1000, retries=(dict(max_attempts=5)))
BEDROCK_MAX_TOKENS = 128000
BEDROCK_TEMPERATURE = 0
sts_client = boto3.client('sts', region_name=AWS_REGION)
ACCOUNT_ID = sts_client.get_caller_identity()["Account"]
# Cross Region Inference for improved resilience https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html  # noqa
BEDROCK_MODEL_ID = "amazon.nova-pro-v1:0"  # Amazon Nova Pro multimodal model

dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name=AWS_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION, config=config)
s3_client = boto3.client('s3', region_name=AWS_REGION, config=config)
secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION, config=config)
s3_resource = boto3.resource('s3', region_name=AWS_REGION)


def invoke_bedrock_agent(
        session_id, query, bedrock_agent='solution', enable_trace=True, end_session=False):
    agent_id = retrieve_environment_variables("BEDROCK_AGENT_ID")
    agent_alias_id = retrieve_environment_variables("BEDROCK_AGENT_ALIAS_ID")

    return bedrock_agent_runtime_client.invoke_agent(
        inputText=query,
        agentId=agent_id,
        agentAliasId=agent_alias_id,
        enableTrace=enable_trace,
        endSession=end_session,
        sessionId=session_id
    )


@st.fragment
def invoke_bedrock_model_streaming(messages, enable_reasoning=False, reasoning_budget=4096):
    # Amazon Nova models use a different request format
    body = {
        "messages": messages,
        "max_tokens": BEDROCK_MAX_TOKENS,
        "temperature": BEDROCK_TEMPERATURE,
    }

    # Note: Amazon Nova models don't support the thinking/reasoning feature like Claude
    # The enable_reasoning parameter is kept for compatibility but not used

    retry_count = 0
    max_retries = 3
    initial_delay = 1
    while retry_count < max_retries:
        try:
            response = bedrock_client.invoke_model_with_response_stream(
                body=json.dumps(body),
                modelId=BEDROCK_MODEL_ID,
                contentType='application/json',
                accept='application/json'
            )

            result = ""
            response_placeholder = st.empty()
            stop_reason = None

            with response_placeholder.container(height=150):
                for event in response['body']:
                    chunk = event.get('chunk')
                    if chunk and 'bytes' in chunk:
                        decoded_chunk = json.loads(chunk['bytes'].decode('utf-8'))
                        if decoded_chunk.get("type") == "content_block_delta":
                            result += decoded_chunk["delta"].get("text", "")
                            response_placeholder.markdown(result)
                        elif decoded_chunk['type'] == 'message_delta':
                            stop_reason = decoded_chunk['delta'].get('stop_reason')

            response_placeholder.empty()
            return result, stop_reason

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'ThrottlingException' or error_code == 'TooManyRequestsException':
                if retry_count == max_retries - 1:
                    raise e  # If this was our last retry, re-raise the exception

                # Calculate exponential backoff delay
                delay = initial_delay * (2 ** retry_count)
                print(f"Rate limit exceeded. Retrying in {delay} seconds... (Attempt {retry_count + 1}/{max_retries})")
                time.sleep(delay)
                retry_count += 1
            else:
                raise e  # Re-raise if it's not a rate limit error


def continuation_prompt(architecture_prompt, prev_response):
    continuation_prompt = f"""
    Please analyze the prompt and initial answer below. The initial answer is cut off due to token limits.
    Provide a continuation relevant to the prompt, starting exactly where the initial answer left off.

    <PROMPT>
    {architecture_prompt}
    </PROMPT>

    <INITIAL ANSWER>
    {prev_response}
    </INITIAL ANSWER>
    """
    return prompts_to_messages(continuation_prompt)


def read_agent_response(event_stream):
    ask_user = False
    agent_answer = ""
    try:
        for event in event_stream:
            if 'chunk' in event:
                data = event['chunk']['bytes']
                agent_answer = data.decode('utf8')
            elif 'trace' in event:
                print(f"orchestration trace = {event['trace']['trace']['orchestrationTrace']}")
                if 'observation' in event['trace']['trace']['orchestrationTrace']:
                    if event['trace']['trace']['orchestrationTrace']['observation']['type'] == "ASK_USER":
                        ask_user = True
                    else:
                        ask_user = False
                else:
                    ask_user = False
            else:
                raise ValueError(f"Unexpected event: {event}")
    except Exception as e:
        raise ValueError(f"Unexpected Error:: {str(e)}")
    return ask_user, agent_answer


def prompts_to_messages(prompts):
    if isinstance(prompts, str):
        return [{"role": "user", "content": prompts}]

    messages = []
    for prompt in prompts:
        messages.append({"role": prompt["role"], "content": prompt["text_prompt"]})
    return messages


def convert_xml_to_html(xml_string):
    html_output = """
    <div class="mxgraph" style="max-width:100%;border:1px solid transparent;" data-mxgraph="{{&quot;highlight&quot;:&quot;#0000ff&quot;,&quot;nav&quot;:true,&quot;resize&quot;:true,&quot;toolbar&quot;:&quot;zoom layers tags lightbox&quot;,&quot;edit&quot;:&quot;_blank&quot;,&quot;xml&quot;:&quot;{text_to_replace}\\n&quot;}}"></div>
    <script type="text/javascript" src="https://www.draw.io/js/viewer.min.js"></script>
    """  # noqa

    root = fromstring(xml_string, forbid_entities=True)
    xml_str_bytes = tostring(root, encoding='utf8', method='xml', xml_declaration=False)
    xml_str = xml_str_bytes.decode('utf-8')

    xml_str = xml_str.replace("&", "&amp;")
    xml_str = xml_str.replace("<", "&lt;")
    xml_str = xml_str.replace(">", "&gt;")
    xml_str = xml_str.replace('"', "\&quot;")  # noqa
    xml_str = xml_str.replace("\n", "\\n")

    final_html_output = html_output.format(text_to_replace=xml_str)
    return final_html_output


# Retrieve feedback
@st.fragment
def collect_feedback(uuid, response, use_case, bedrock_model_name):
    FEEDBACK_TABLE_NAME = retrieve_environment_variables("FEEDBACK_TABLE_NAME")
    selected = st.feedback("thumbs", key=f"s-{uuid}")
    if selected is not None:
        print("about to write to dynamo")
        text = st.text_input(
            f"fe-{uuid}", label_visibility="hidden",
            placeholder="[MANDATORY] Please provide an explanation to submit the feedback",
        )
        if text:
            print(f"feedback sentiment: {selected}. feedback explanation: {text}.")
            print(f"uuid: {uuid}. conversation_id: {st.session_state['conversation_id']}")
            print(f"bedrock_model_name: {bedrock_model_name}. use_case: {use_case}.")
            current_datetime = datetime.datetime.now(tz=datetime.timezone.utc)
            current_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
            item = {
                'conversation_id': st.session_state['conversation_id'],
                'uuid': uuid,
                'feedback': selected,
                'feedback_explanation': text,
                'response': response,
                'conversation_time': current_datetime,
                'bedrock_model': bedrock_model_name,
                'use_case': use_case
            }
            feedback_table = dynamodb_resource.Table(FEEDBACK_TABLE_NAME)
            print(f"About to write item to dynamodb: {item}")
            feedback_table.put_item(Item=item)
            print(f"updated item in DynamoDB table: {FEEDBACK_TABLE_NAME}")
            sentiment_mapping = [":material/thumb_down:", ":material/thumb_up:"]
            st.markdown(f"Feedback rating: {sentiment_mapping[selected]}. Feedback text: {text}")


def retrieve_environment_variables(key):
    ssm_parameter = json.loads(os.getenv("AWS_RESOURCE_NAMES_PARAMETER"))
    return ssm_parameter[key]


def retrieve_cognito_details(key):
    response = secrets_client.get_secret_value(SecretId=retrieve_environment_variables("COGNITO_SECRET_ID"))
    cognito_details = json.loads(response['SecretString'])
    return cognito_details[key]


# Store conversation details in DynamoDB
def save_conversation(conversation_id, prompt, response):
    CONVERSATION_TABLE_NAME = retrieve_environment_variables("CONVERSATION_TABLE_NAME")
    item = {
        'conversation_id': conversation_id,
        'uuid': str(uuid.uuid4()),
        'user_response': prompt,
        'assistant_response': response,
        'conversation_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    }
    dynamodb_resource.Table(CONVERSATION_TABLE_NAME).put_item(Item=item)


# Store conversation details in DynamoDB
def save_session(conversation_id, name, email):
    SESSION_TABLE_NAME = retrieve_environment_variables("SESSION_TABLE_NAME")
    item = {
        'conversation_id': conversation_id,
        'user_name': name,
        'user_email': email,
        'aws_midway_user_name': st.session_state.midway_user,
        'session_start_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    }
    dynamodb_resource.Table(SESSION_TABLE_NAME).put_item(Item=item)


# Store conversation details in DynamoDB
def update_session(conversation_id, presigned_url):
    SESSION_TABLE_NAME = retrieve_environment_variables("SESSION_TABLE_NAME")
    response = dynamodb_resource.Table(SESSION_TABLE_NAME).update_item(
        Key={
            'conversation_id': conversation_id
        },
        UpdateExpression='SET presigned_url = :url, session_update_time = :update_time',
        ExpressionAttributeValues={
            ':url': presigned_url,
            ':update_time': datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        },
        ReturnValues="UPDATED_NEW"
    )

    return response


# Store content in S3
def store_in_s3(content, content_type):
    S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")
    print(f"Bucket Name: {S3_BUCKET_NAME}")
    current_datetime = datetime.datetime.now(tz=datetime.timezone.utc)
    current_datetime = current_datetime.strftime("%Y%m%d-%H%M%S")
    object_name = f"{st.session_state['conversation_id']}/{content_type}-{current_datetime}.md"
    s3_client.put_object(Body=content, Bucket=S3_BUCKET_NAME, Key=object_name)


# Zip files in S3 pertaining to conversation
def create_artifacts_zip(object_name):
    # Creating tmp file
    tmpdir = tempfile.mkdtemp()
    # saved_umask = os.umask(0o077)

    S3_BUCKET_NAME = retrieve_environment_variables("S3_BUCKET_NAME")
    conversation_id = st.session_state['conversation_id']
    # create directory locally to store s3 artifacts
    Path(f"{tmpdir}/{conversation_id}").mkdir(parents=True, exist_ok=True)
    print(f"Created directory: {tmpdir}/{conversation_id}")

    # download objects from S3 pertaining to the current conversation
    bucket = s3_resource.Bucket(S3_BUCKET_NAME)
    conversation_artifacts = list(bucket.objects.filter(Prefix=conversation_id))
    for artifact in conversation_artifacts:
        out_name = f"{tmpdir}/{conversation_id}/{artifact.key.split('/')[-1]}"
        bucket.download_file(artifact.key, out_name)
    print(f"Downloaded artifacts from S3 for conversation: {conversation_id}")

    # Create zip file with all transcript artifacts
    directory = f"{tmpdir}/{conversation_id}/"
    file_format = "*.md"
    files_to_zip = glob.glob(directory + file_format)
    with zipfile.ZipFile(f"{tmpdir}/{conversation_id}/{object_name}", 'w') as zip_file:
        for file in files_to_zip:
            zip_file.write(file, arcname=f"{conversation_id}/{os.path.basename(file)}")

    print(f"Created zip file: {object_name}")

    # Store the zip file in S3
    file_path = f"{conversation_id}/{object_name}"
    print(f"Uploading {file_path} to S3 bucket: {S3_BUCKET_NAME}")
    s3_client.upload_file(f"{tmpdir}/{file_path}", S3_BUCKET_NAME, file_path)
    return tmpdir, file_path

# Enable option to download conversation history
@st.fragment
def enable_artifacts_download():
    # Set up column for button
    left, _, _ = st.columns(3)
    
    # Show the "Download artifacts" button
    download_button = left.button("Download artifacts")
    
    # If button is clicked, generate artifacts
    if download_button:
        with st.spinner("Preparing your artifacts..."):
            # Build the transcript
            tmp_transcript = ["# Transcript"]
            for interaction in st.session_state.interaction:
                tmp_transcript.append(f"## {interaction['type']}")
                tmp_transcript.append(f"{interaction['details']}")
            
            transcript = '\n\n'.join(str(x) for x in tmp_transcript)
            
            # Upload transcript to S3
            S3_BUCKET_NAME = retrieve_environment_variables('S3_BUCKET_NAME')
            transcript_object_name = f"{st.session_state['conversation_id']}/transcript.md"
            s3_client.put_object(Body=transcript, Bucket=S3_BUCKET_NAME, Key=transcript_object_name)
            
            # Create a zip file with all artifacts
            download_transcript_zip_file = "conversation_artifacts.zip"
            tmpdir, file_path = create_artifacts_zip(download_transcript_zip_file)
            
            # Read the zip file into memory
            with open(f"{tmpdir}/{file_path}", 'rb') as f:
                artifact_data = f.read()
            
            # Clean up temporary files
            try:
                shutil.rmtree(f"{tmpdir}/{st.session_state['conversation_id']}")
                os.rmdir(tmpdir)
            except OSError:
                pass
            
            # Show success message
            st.success("Your artifacts are ready!")
            
            # Create a download link instead of a button
            b64 = base64.b64encode(artifact_data).decode()
            href = f"data:application/zip;base64,{b64}"
            st.markdown(
                f'<a href="{href}" download="conversation_artifacts.zip" style="color:#0066cc;text-decoration:underline;">Click here to download the artifacts</a>', 
                unsafe_allow_html=True
            )