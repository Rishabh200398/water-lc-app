# Prompts I used to build this project (Claude Code)

The main prompts I typed while building Water LC Ops Copilot, in order. Lightly trimmed.

1. "Create a folder called AI-Final project and have a folder on Water LC app."
2. "Read this [CLAUDE.md] and put this md in the folder… get ready, we will be starting the project."
3. "The app needs to be created with a similar set up like our homework 5 and 4. So get the .env file from there and also the information on the type of gpt model you need to be using."
4. "How can the Water LC app be different from an event planner? … we need to find the speakers, set the theme, create posters, market the event, set a budget (travel, stay, honorarium, lunch)… confirmation from our advisor Jim… a newsletter… is there a way to make it beyond event planning?"
5. "I need to sell this idea to Erika, can you draft a note on the high-level features and utility?"
6. "Is there a way I can make an app that counts the amount of water that is consumed for every prompt run?"
7. Described our full process: brainstorm water-sector events (Lunch and Learns, field visits, career treks) → find Yale/YSE/SOM alumni speakers (virtual preferred) → meet them → budget ($15,000/yr, $7,500/semester, minus co-lead wages at $21/h, max 10 h/person/week) → date on the YSE calendar and a room → poster and marketing two weeks ahead on Yale Connect and WhatsApp → catering from our list, a different cuisine each time, always vegetarian/vegan → Jim approves, Cristina orders → photos → monthly newsletter (recaps, jobs, conferences, water news global/national/CT, Water Spotlight) → collaborate with other LCs → a public website with an admin login.
8. Shared the YSE academic calendar, our caterer list, last year's co-lead timesheets and overall budget, the September and October newsletters, and the Fall Splash word cloud ("the largest ones are the ones with most priority").
9. "We usually budget 200 bucks for an event that has 20 odd people." / "The budget has reduced from last year." / "No need to keep their names."
10. "How many agents would this app have? I want the end-to-end process done by AI with only me and Erika giving permission to send email, review the newsletter etc."
11. "Go with A [open approved emails as drafts in my mail app] and C's outbox log. Make the app user friendly, it should open on web and mobile and should have a water theme to it."
12. "I cannot login." (Fixed: after signing in from the "Co-lead login" link the page didn't refresh.)
13. "The brief me function is not working." (Cause: a dropped connection to Portkey. Added automatic retries and a clear error message.)
14. "I want the ability to re-run the agent to brainstorm some new ideas for the event too." (Added "Brainstorm new ideas" with optional feedback and an "Earlier ideas" list to switch back.)
15. "Where is the brainstorm button?" (It only showed at one step; made rethinking available until the date is confirmed.)
16. Asked for a clearer, step-by-step event flow: the app asks questions first (event, seminar, student-led webinar, career session or field visit; collaboration yes/no via a radio button, never forced); a research agent reads current news, what students want and what we've done and feeds the idea agent; pick from the ideas; find relevant YSE alumni speakers (East Coast / near New York for in-person); approve or edit the list; an email in my own words asking for a time; I paste meeting notes and confirm the date so the idea is never brainstormed again; budget first (virtual = catering only, field visit = student travel), then an itemized catering order with item prices and a total, with the option to re-run either.
17. "What should be in the report and slides?" then shared Erika's quote and my time estimate (a week of research per Lunch and Learn by hand vs. about a day with the tool) and approved a public repo.
18. Shared the professor's update: submit only report.html, slides.html and an optional video; the GitHub URL must be in both files.
