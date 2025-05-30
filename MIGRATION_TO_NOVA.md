# Migration to Amazon Nova Models

This document summarizes the changes made to migrate the DevGenius application from Claude models to Amazon Nova models.

## Changes Made

### 1. Model Configuration Updates

**File: `chatbot/agent.py`**
- Line 36: Updated `BEDROCK_MODEL_ID` from Claude 3.5 Sonnet to `amazon.nova-pro-v1:0`

**File: `chatbot/utils.py`**
- Line 26: Updated `BEDROCK_MODEL_ID` from Claude 3.7 Sonnet to `amazon.nova-pro-v1:0`
- Lines 52-61: Removed Anthropic-specific API parameters (`anthropic_version`, `thinking` feature)

**File: `lib/index.ts`**
- Line 39: Updated `BEDROCK_AGENT_FOUNDATION_MODEL` to `amazon.nova-pro-v1:0`
- Line 511: Removed `anthropic_version` from the prompt template configuration

### 2. Documentation Updates

**File: `README.md`**
- Line 3: Updated description to mention "Amazon Nova AI models" instead of "Claude AI models"
- Line 25: Updated AI Engine description to reference "Amazon Nova AI models"
- Line 43: Updated prerequisites to mention "Amazon Nova Pro" instead of Claude models

**File: `chatbot/cost_estimate_widget.py`**
- Line 89: Updated cost estimation disclaimer to mention "Amazon Nova Model" instead of "Claude Model"

**File: `chatbot/layout.py`**
- Line 52: Updated disclaimer to mention "Amazon Nova via Bedrock" instead of "Claude via Bedrock"

## Why Amazon Nova Pro?

Amazon Nova Pro was selected as the replacement model because:

1. **Multimodal Capabilities**: The application processes both text and images (architecture diagrams), which Nova Pro supports
2. **High-Quality Reasoning**: Nova Pro provides excellent performance for complex AWS solution generation
3. **Cost-Effectiveness**: Nova models are optimized for cost while maintaining high quality
4. **AWS Native**: Being an Amazon model, it integrates seamlessly with other AWS services

## API Compatibility

The migration maintains compatibility with existing code by:
- Using the unified Bedrock `converse_stream` API which works with both Claude and Nova models
- Keeping the same message format structure
- Maintaining the same streaming response handling

## Testing Recommendations

After deployment, verify:
1. Text-based conversations work correctly
2. Image upload and analysis functionality works
3. Architecture diagram generation produces quality results
4. Cost estimation and documentation generation work as expected
5. All widget functionalities (CDK, CloudFormation, Terraform generation) work properly

## Rollback Plan

If issues arise, the migration can be rolled back by:
1. Reverting the `BEDROCK_MODEL_ID` values to the original Claude model IDs
2. Restoring the `anthropic_version` parameter in the API calls
3. Re-adding the thinking/reasoning configuration if needed

## Notes

- The `enable_reasoning` parameter is kept for compatibility but not used with Nova models
- Nova models use a simpler API format without the Anthropic-specific version parameter
- All existing functionality should work seamlessly with the new model