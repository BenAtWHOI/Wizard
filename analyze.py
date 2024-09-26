import anthropic
import argparse
import fnmatch
import os
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry
import time

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
        print("Rate limit reached. Waiting for 60 seconds before retrying...")
        time.sleep(60)
        return analyze_batch(client, prompt, files_batch)

def interactive_loop(client, prompt, files, initial_message):
    # Store initial analysis
    if not isinstance(initial_message, str):
        initial_message = initial_message.content[0].text
    conversation = [
        {"role": "user", "content": [{"type": "text", "text": files}]},
        {"role": "assistant", "content": initial_message}
    ]
    print("\nYou can now ask questions about the codebase. Type 'exit' to quit.")

    # Keep asking questions until exit
    while True:
        user_input = input("\nYour question: ")
        if user_input.lower() == 'exit':
            break

        # Ask question
        conversation.append({"role": "user", "content": user_input})
        response = client.messages.create(model="claude-3-5-sonnet-20240620", max_tokens=1000, temperature=0, system=prompt, messages=conversation)

        # Retrieve and store response
        print(f'\nClaude response:\n{response.content[0].text}')
        conversation.append({"role": "assistant", "content": response.content[0].text})

    print("Exiting the interactive loop.")

def main(skip_analysis):
    # API key
    load_dotenv()
    api_key = os.environ['API_KEY']

    # Config
    prompt = os.environ['PROMPT']
    override_limit = os.environ['OVERRIDE_LIMIT']
    directory = os.environ['DIRECTORY']
    file_limit = os.environ['FILE_LIMIT']
    max_lines = int(os.environ['MAX_LINES'])
    include_files = os.environ['INCLUDE_FILES']
    limit_lines_files = os.environ['LIMIT_LINES_FILES']

    # Safety feature
    if override_limit.lower() == 'true':
        confirmation = input("Are you sure you want to override the limit? Type 'Confirm override' to proceed.")
        if confirmation != 'Confirm override':
            override_limit = False

    # Read all file names and content into string
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

    # Store file data
    with open('files.txt', 'w') as file:
        file.write(files)
    
    client = anthropic.Anthropic()

    # Skip analysis if requested
    if skip_analysis:
        return client, prompt, files, None

    
    # Split files into batches
    batch_size = 5  # Adjust this based on your needs
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
                
                if len(current_batch) + len(file_content) > 100000:  # Adjust this threshold as needed
                    file_batches.append(current_batch)
                    current_batch = file_content
                else:
                    current_batch += file_content
    
    if current_batch:
        file_batches.append(current_batch)

    # Analyze each batch
    full_analysis = ""
    for i, batch in enumerate(file_batches):
        print(f"Analyzing batch {i+1} of {len(file_batches)}...")
        analysis = analyze_batch(client, prompt, batch)
        full_analysis += f"\n\nBatch {i+1} Analysis:\n{analysis}"
        time.sleep(60)  # Wait between batches to respect rate limits

    # Store full analysis
    with open('claude.txt', 'w') as file:
        file.write(full_analysis)

    print("Analysis complete. You can now start the interactive loop.")
    return client, prompt, files, full_analysis

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip_analysis', action='store_true', help='Do not run codebase analysis if set')
    args = parser.parse_args()

    client, prompt, files, initial_message = main(args.skip_analysis)

    if args.skip_analysis:
        with open('claude.txt') as file:
             initial_message = str([line.rstrip() for line in file])

    print(initial_message)

    interactive_loop(client, prompt, files, initial_message)