from prompt_toolkit import PromptSession

session = PromptSession()

while True:
    text = session.prompt("You> ")
    if text == "exit":
        break
    print(text)
