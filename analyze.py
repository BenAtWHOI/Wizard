import anthropic
import argparse
import fnmatch
import os
from dotenv import load_dotenv

def interactive_loop(client, prompt, files, initial_message):
    # Store initial analysis
    conversation = [
        {"role": "user", "content": [{"type": "text", "text": files}]},
        {"role": "assistant", "content": initial_message.content[0].text}
    ]
    print("\nYou can now ask questions about the codebase. Type 'exit' to quit.")

    # Keep asking questions until exit
    while True:
        user_input = input("\nYour question: ")
        if user_input.lower() == 'exit':
            break

        # Ask question
        conversation.append({"role": "user", "content": user_input})
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0,
            system=prompt,
            messages=conversation
        )

        # Retrieve and store response
        print(f'\nClaude response:\n{response.content[0].text}')
        conversation.append({"role": "assistant", "content": response.content[0].text})

    print("Exiting the interactive loop.")

def main():
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

    # Make call to claude
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=500,
        temperature=0,
        system=prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": files
                    }
                ]
            }
        ]
    )
    print(message.content)

    # Store response
    with open('claude.txt', 'w') as file:
        file.write(message.content[0].text)

    return client, prompt, files, message

if __name__ == '__main__':
    client, prompt, files, initial_message = main()
    interactive_loop(client, prompt, files, initial_message)