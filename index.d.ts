import { Construct } from 'constructs';
import * as cdk from 'aws-cdk-lib';
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
export declare class VitruvioStack extends cdk.Stack {
    readonly Distribution: cloudfront.Distribution;
    private readonly BEDROCK_KNOWLEDGE_BASE_SOURCES;
    private readonly BEDROCK_KB_INDEX_NAME;
    private readonly BEDROCK_AGENT_FOUNDATION_MODEL;
    private readonly BEDROCK_AGENT_INSTRUCTION;
    private readonly BEDROCK_AGENT_ORCHESTRATION_INSTRUCTION;
    constructor(scope: Construct, id: string, props: cdk.StackProps);
    private addTags;
    private addOutputs;
}
