# **Mail Agent Project Plan**

## **1. Project Goals**

- **Categorize Emails:** Automatically tag emails into categories (e.g., Family, Work, Personal, Spam).
- **Assign Priority:** Assign priority levels (e.g., Urgent, High, Normal, Low).
- **Extract Deadlines:** Detect and parse deadlines or actions from emails.
- **Calendar Integration:** Add deadlines to Google/Outlook Calendar.
- **Efficiency:** Ensure emails are processed only once and fetched hourly.

---

## **2. Architecture Design**

### **2.1 High-Level Architecture**

#### **Components:**

1. **Email Fetcher:** Fetches emails from Gmail/Outlook API.
2. **Status Tracker:** Marks processed emails using email tags or folders.
3. **Preprocessor:** Cleans and prepares email content for processing.
4. **Classification Agent:** Categorizes emails and assigns priority.
5. **Deadline Extraction Agent:** Detects and parses deadlines.
6. **Calendar Integrator:** Adds events to Google/Outlook Calendar.
7. **Workflow Orchestrator:** Manages the pipeline using LangGraph.

---

## **3. Workflow Flow**

1. **Fetch Emails:** Use Gmail/Outlook API to fetch unread emails hourly, excluding those tagged or moved to the processed folder.
2. **Preprocess Emails:** Clean email content, remove HTML tags, and extract text.
3. **Classify Emails:** Use Llama 3 8B locally to categorize and assign priority.
4. **Extract Deadlines:** Detect deadlines using LLM and parse dates using `dateparser`.
5. **Add to Calendar:** Create a calendar event if a deadline is detected.
6. **Mark as Processed:** Tag the email or move it to the processed folder.
7. **Logging & Error Handling:** Log errors and retry failed emails.

---

## **4. Technology Stack**

- **Language:** Python
- **LLM Framework:** LangChain, LangGraph
- **Local LLM:** Llama 3 8B-instruct (quantized with GGUF)
- **Quantization Tool:** `llama.cpp`
- **Email APIs:** Gmail API, Microsoft Graph API
- **Date Parsing:** `dateparser`, `parsedatetime`
- **Calendar Integration:** Google Calendar API, Microsoft Graph API

---

## **5. Development Phases**

1. **Setup & Email Fetching:** Configure APIs, authenticate, and fetch unread emails.
2. **Preprocessing & Classification:** Clean content and classify emails using LLM.
3. **Deadline Extraction & Calendar Integration:** Extract deadlines and add events.
4. **Workflow Orchestration:** Use LangGraph to manage and automate the workflow.
5. **Testing & Optimization:** Test with sample emails, optimize prompts, and fine-tune if needed.
6. **Deployment:** Schedule the agent using cron or Task Scheduler, and monitor logs.

---

## **6. Key Considerations**

- **Privacy & Security:** Use local LLM inference, encrypt API tokens, and limit API scopes.
- **Scalability:** Process multiple emails in parallel, and optimize LLM inference speed.
- **Error Handling:** Implement retry logic and handle edge cases like ambiguous deadlines.

---

## **7. Using Email Tags or Folders Instead of SQLite**

### **1. Use Gmail Labels or Outlook Folders**

- **Gmail:** Apply a label like `ProcessedByAgent` after processing.
- **Outlook:** Move processed emails to a folder like `Processed` or use categories.

### **2. Use Email Flags**

- Set a custom flag to indicate processed status and filter future fetches.

### **3. Store Processed State in Email Headers**

- If supported, add a custom header like `X-Processed-By: MyMailAgent`.

---

## **8. Integration into Workflow**

1. **Fetch Unread Emails:** Exclude emails with the `ProcessedByAgent` label or in the `Processed` folder.
2. **Process Emails:** Preprocess, classify, and extract deadlines.
3. **Calendar Integration:** Add deadlines to Google/Outlook Calendar.
4. **Mark as Processed:** Tag the email or move it to the processed folder.
5. **Logging & Error Handling:** Retry failed emails and log issues.

---

## **9. Future Enhancements**

- **Fine-Tuning:** Use LoRA for better classification and deadline extraction.
- **Spam Filtering:** Add a dedicated spam detection agent.
- **Task Management:** Integrate with Todoist or Trello.
- **Multi-Language Support:** Enable non-English email processing.

---

## **10. Conclusion**

This modular design ensures clear separation of functionalities and efficient email processing. Using email tags or folders for tracking simplifies the workflow by eliminating the need for a local database, making the system more streamlined and maintainable.
