# Life Health CRM - AI-Powered Healthcare Ecosystem

## 🌍 Vision: Revolutionizing Real-World Healthcare
Life Health CRM is designed to eliminate paperwork and digitize the entire healthcare journey ("No paperwork, all data electrified"). It bridges the gap between urban medical facilities and rural healthcare needs through advanced AI agents and robust offline-first mobile solutions.

---

## 🚀 Key Features & Real-World Impact

### 1. 🏥 Smart Appointment & Consultation
*   **Problem:** Patients often don't know which specialist to consult for their symptoms.
*   **Solution:** AI-powered **SummarizeAgent** analyzes patient symptoms and automatically suggests the right doctor and available time slots.
*   **Impact:** Reduces triaging time and ensures patients see the correct specialist immediately.

### 2. 📄 Intelligent Medical Record Analysis
*   **Problem:** Doctors lack time to study lengthy, complex past medical reports. Applications often fail to digitize old physical records.
*   **Solution:** **DocAgent** & **MedGemma** allow doctors to upload previous reports (PDF/Images). The AI instantly summarizes patient history, medications, and key findings.
*   **Impact:** Enables evidence-based diagnosis in seconds, preventing medication errors from overlooked history.

### 3. 🎙️ MedASR: Voice-to-Records
*   **Feature:** Doctors can record patient consultations in real-time.
*   **Capability:** **MedASR** (Medical Automatic Speech Recognition) transcribes the conversation and automatically extracts medications and lab tests to populate the prescription.
*   **Impact:** Allows doctors to focus on the patient instead of typing, improving the doctor-patient relationship and record accuracy.

### 4. 🏘️ Rural Healthcare & Offline Capabilities (Nurse App)
*   **Challenge:** Rural areas often lack internet infrastructure and expensive diagnostic tools.
*   **Solution:** A mobile app for nurses (Government/NGOs) that works **completely offline**.
    *   **Vitals Monitoring:** Nurses record BP, SpO2, etc. If vitals are abnormal (e.g., low BP), **MedGemma** alerts the doctor with patient details.
    *   **Data Sync:** Data stored locally syncs with the central server once the nurse reaches an area with internet access.
*   **Impact:** Prevents conflicting treatments (e.g., prescribing BP meds when BP is already low) and ensures continuous care in remote camps even without connectivity.

### 5. 📞 AI Voice Agent for Follow-ups & Reminders
*   **Feature:** Automated, human-like voice calls for patient follow-ups.
*   **Use Cases:**
    *   **Vaccination Reminders:** Calls parents for child (or pet) vaccination due dates.
    *   **Appointment Booking:** Can book appointments during the call if the patient agrees.
    *   **Multilingual Support:** Converses in the patient's local language.
*   **Impact:** drastically reduces missed vaccinations and follow-ups, directly improving public health outcomes (e.g., child immunization rates).

### 6. 🧠 Deep Research for Complex Cases
*   **Feature:** **DeepResearch Agent** integrated with MedASR, HeAR (Health Acoustic Representations), and MedGemma.
*   **Capability:** Conducts deep analysis of patient data to provide diagnostic insights, especially useful in complex cases or where specialist access is limited.
*   **Impact:** Acts as a "second opinion" or research assistant for doctors, enhancing diagnostic accuracy in resource-constrained settings.

### 7. 🎓 Knowledge Sharing (Junior Doctor Support)
*   **Problem:** Junior doctors may lack the experience of senior specialists.
*   **Solution:** The system stores and indexes historical treatment patterns and senior doctor suggestions ("GenAI Insights").
*   **Impact:** Junior doctors can search and learn from successful past treatments and senior doctor notes, standardizing quality of care across the institution.

### 8. 🔍 Patient Empowerment
*   **Feature:** Patients can upload their own reports and ask **MedGemma** to explain them in simple terms.
*   **Impact:** Demystifies medical jargon, helping patients understand their health condition and improving treatment adherence.

---

## 🤖 The AI Agent Ecosystem

1.  **VoiceAgent:** Handles multilingual translations and outbound calls.
2.  **SummarizeAgent:** Triage and doctor recommendation based on symptoms.
3.  **DocAgent:** Document analysis and explanation.
4.  **DeepAgent:** Deep medical research and complex diagnostics.
5.  **CallAgent:** Manages telephonic appointments and reminders.

---

## 🛠️ Roles

*   **Admin:** Manages the entire facility and user roles.
*   **Doctor:** Consults, diagnoses, and views AI insights.
*   **Nurse:** Field work, vitals collection (Offline capable).
*   **Lab:** Uploads test reports.
*   **Patient:** Books appointments, views history, and interacts with AI for explanations.

---

*Powered by Advanced AI: MedGemma, MedASR, HeAR, and Custom LLU (Large Language Understanding) Models.*

### 9. 🧠 Expert Agent (Hospital Knowledge Base)
*   **Feature:** A shared knowledge repository where senior doctors can contribute insights, successful treatment protocols, and key findings.
*   **Capability:**
    *   **Contextual Search:** Junior doctors can search for symptoms or conditions.
    *   **Hospital-Specific Priority:** The AI prioritizes treatment data (medications/lab tests) from the *same* hospital to ensure protocol consistency.
    *   **Global Insights:** If local data is scarce, it fetches anonymized insights from other hospitals (hiding sensitive medication/lab details) to provide a broader clinical perspective.
*   **Impact:** Democratizes medical expertise, standardizes care quality, and helps junior doctors make informed decisions even in the absence of senior supervision.

---

## 🏗️ Technical Architecture & API

The backend is built with **FastAPI** for high performance and async capabilities, essential for real-time AI processing.

### 🔌 Core API Endpoints

#### 1. AI Agents Layer (`/api/v1/agent`)
*   **Deep Research:** `POST /deep-research`
    *   **Input:** Image, Audio, PDF, Vision Prompt.
    *   **Output:** Streaming Server-Sent Events (SSE) with real-time tokens (`data: {"type": "token", ...}`).
    *   **Use Case:** Complex diagnostics where the model researches symptoms, analyzes images/PDFs, and browses the web (Tavily) for medical consensus.
*   **Expert Knowledge:** `GET /expert-check` & `POST /expert-check`
    *   **Input (POST):** Insight text, Category, Medications, Lab Tests.
    *   **Use Case:** Senior doctors contributing knowledge; Junior doctors searching for similar cases.
    *   **Tech:** Uses **Pinecone** vector database with **Llama-text-embed-v2** embeddings for semantic search.
*   **Appointment Suggestion:** `POST /suggest-appointment`
    *   **Input:** Patient description (symptoms), date.
    *   **Output:** Recommended doctor, specialization, and time slots.
    *   **Use Case:** Smart triaging for patients.
*   **Document Analysis:** `POST /analyze`
    *   **Input:** Document URL, question.
    *   **Output:** Streaming text response explaining the report.
    *   **Use Case:** Patient understanding reports or doctors quickly reviewing history.
*   **Outbound Call Trigger:** `POST /trigger-call`
    *   **Input:** Phone number, appointment ID.
    *   **Output:** Initiates a SIP call via LiveKit.
    *   **Use Case:** Vaccination reminders, appointment confirmations.

#### 2. Real-Time Voice Layer (`/api/v1/voice`)
*   **WebSocket Transcription:** `WS /ws/transcribe`
    *   **Protocol:** Binary audio frames (16kHz PCM/WAV) -> Real-time transcription events.
    *   **Use Case:** Doctor dictation during consultation (MedASR).
*   **File Transcription:** `POST /transcribe`
    *   **Input:** Audio file (WAV/MP3).
    *   **Output:** Full text transcript.
    *   **Use Case:** Uploading voice notes from offline nurse visits.

#### 3. Core Entities (`/api/v1/*`)
*   **Events:** `PUT /events/{id}` - Update event data (used for tracking patient vitals/alerts).
*   **Patients/Doctors/Nurses:** Standard CRUD endpoints for managing ecosystem roles.

### 📱 Offline-First Architecture (Nurse App)
*   **Local Database:** The mobile app uses a local SQLite/Realm database to store patient vitals and logs.
*   **Sync Mechanism:** When internet is available, the app calls `POST /api/v1/events` or `POST /api/v1/patients/sync` (conceptual) to upload pending records.
*   **Edge AI:** Lighter models (e.g., quantized MedGemma/Lite) run on the device for immediate vital analysis (BP/SpO2 alerts) without server round-trip.
