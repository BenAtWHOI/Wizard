import anthropic
import argparse
import fnmatch
import os
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=1, period=60)
def rate_limited_api_call(client, model, max_tokens, temperature, system, messages):
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages
    )

def truncate_content(content, max_chars=100000):
    if len(content) > max_chars:
        return content[:max_chars] + "\n...[Content truncated due to length]..."
    return content

def analyze_batch(client, prompt, files_batch):
    truncated_files = truncate_content(files_batch)
    try:
        message = rate_limited_api_call(client, "claude-3-5-sonnet-20240620", 500, 0, prompt, [{"role": "user", "content": [{"type": "text", "text": truncated_files}]}])
        return message.content[0].text
    except anthropic.RateLimitError:
        print("Rate limit reached. Retrying...")
        return analyze_batch(client, prompt, files_batch)

def complete_analysis(client, prompt, full_analysis):
    try:
        message = rate_limited_api_call(
            client,
            "claude-3-5-sonnet-20240620",
            1000,
            0,
            prompt,
            [{"role": "user", "content": [{"type": "text", "text": f"Here's the full analysis of all batches. Please provide a comprehensive summary and analysis of the entire codebase based on this information:\n\n{full_analysis}"}]}]
        )
        return message.content[0].text
    except anthropic.RateLimitError:
        print("Rate limit reached. Retrying complete analysis...")
        return complete_analysis(client, prompt, full_analysis)

def interactive_loop(client, prompt, files, initial_message):
    if not isinstance(initial_message, str):
        initial_message = initial_message.content[0].text
    conversation = [
        {"role": "user", "content": [{"type": "text", "text": files}]},
        {"role": "assistant", "content": initial_message}
    ]
    print("\nYou can now ask questions about the codebase. Type 'exit' to quit.")

    while True:
        user_input = input("\nYour question: ")
        if user_input.lower() == 'exit':
            break

        conversation.append({"role": "user", "content": user_input})
        response = client.messages.create(model="claude-3-5-sonnet-20240620", max_tokens=1000, temperature=0, system=prompt, messages=conversation)

        print(f'\nClaude response:\n{response.content[0].text}')
        conversation.append({"role": "assistant", "content": response.content[0].text})

    print("Exiting the interactive loop.")

def main(skip_analysis):
    load_dotenv()
    prompt = os.environ['PROMPT']
    override_limit = os.environ['OVERRIDE_LIMIT']
    directory = os.environ['DIRECTORY']
    file_limit = os.environ['FILE_LIMIT']
    max_lines = int(os.environ['MAX_LINES'])
    include_files = os.environ['INCLUDE_FILES']
    limit_lines_files = os.environ['LIMIT_LINES_FILES']

    if override_limit.lower() == 'true':
        confirmation = input("Are you sure you want to override the limit? Type 'Confirm override' to proceed.")
        if confirmation != 'Confirm override':
            override_limit = False

    files = ""
    allowed_patterns = include_files.split(',')
    limit_lines_patterns = limit_lines_files.split(',')
    for root, dirs, filenames in os.walk(directory):
        i = 0
        if not override_limit and i >= file_limit:
            break
        for filename in filenames:
            if any(fnmatch.fnmatch(filename, pattern.strip()) for pattern in allowed_patterns):
                file_path = os.path.join(root, filename)
                files += f"====================================================================================================\n{file_path}\n"
                try:
                    with open(file_path, 'r', errors='replace') as file:
                        j = 0
                        for line in file:
                            files += line
                            j += 1
                            if any(fnmatch.fnmatch(filename, pattern.strip()) for pattern in limit_lines_patterns) and j >= max_lines:
                                break
                except Exception as e:
                    files += f"Error reading file: {str(e)}\n"
        i += 1

    with open('files.txt', 'w') as file:
        file.write(files)

    client = anthropic.Anthropic()

    if skip_analysis:
        try:
            with open('claude_complete.txt', 'r') as file:
                initial_message = file.read()
        except FileNotFoundError:
            print("Complete analysis file not found. Please run without --skip_analysis first.")
            return
    else:
        batch_size = 5
        file_batches = []
        current_batch = ""

        for root, dirs, filenames in os.walk(directory):
            for filename in filenames:
                if any(fnmatch.fnmatch(filename, pattern.strip()) for pattern in allowed_patterns):
                    file_path = os.path.join(root, filename)
                    file_content = f"====================================================================================================\n{file_path}\n"
                    try:
                        with open(file_path, 'r', errors='replace') as file:
                            j = 0
                            for line in file:
                                file_content += line
                                j += 1
                                if any(fnmatch.fnmatch(filename, pattern.strip()) for pattern in limit_lines_patterns) and j >= max_lines:
                                    break
                    except Exception as e:
                        file_content += f"Error reading file: {str(e)}\n"

                    if len(current_batch) + len(file_content) > 100000:
                        file_batches.append(current_batch)
                        current_batch = file_content
                    else:
                        current_batch += file_content

        if current_batch:
            file_batches.append(current_batch)

        full_analysis = ""
        for i, batch in enumerate(file_batches):
            print(f"Analyzing batch {i+1} of {len(file_batches)}...")
            analysis = analyze_batch(client, prompt, batch)
            full_analysis += f"\n\nBatch {i+1} Analysis:\n{analysis}"

        with open('claude_batches.txt', 'w') as file:
            file.write(full_analysis)

        print("Performing complete analysis of all batches...")
        complete_analysis_result = complete_analysis(client, prompt, full_analysis)

        with open('claude_complete.txt', 'w') as file:
            file.write(complete_analysis_result)

        print("Complete analysis finished.")
        initial_message = complete_analysis_result

    print(initial_message)

    interactive_loop(client, prompt, files, initial_message)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip_analysis', action='store_true', help='Skip codebase analysis if set')
    args = parser.parse_args()

    main(args.skip_analysis)