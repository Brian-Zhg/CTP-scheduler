export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { promptText, currentDate } = req.body;
    const apiKey = process.env.GEMINI_API_KEY;

    if (!apiKey) {
        return res.status(500).json({ error: 'API key not found in Vercel environment' });
    }

    try {
        const systemInstruction = `
            You are a scheduling assistant. The user will provide a text describing events.
            The current date and time is ${currentDate}.
            Extract the events and return ONLY a valid JSON array of objects. 
            Do not include markdown blocks like \`\`\`json.
            Each object must have exactly these keys:
            - "title": A short string title of the event.
            - "start": An ISO 8601 formatted date-time string.
            - "end": An ISO 8601 formatted date-time string.
        `;

        const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: `${systemInstruction}\n\nUser Input: ${promptText}` }] }]
            })
        });

        const data = await response.json();

        // Catch API-level errors (like an invalid key)
        if (!response.ok) {
            console.error("Gemini API Error:", data);
            return res.status(500).json({ error: data.error?.message || 'Gemini API rejected the request.' });
        }

        // Catch empty or blocked responses
        if (!data.candidates || data.candidates.length === 0) {
            console.error("Empty response:", data);
            return res.status(500).json({ error: 'Gemini returned an empty response.' });
        }
        
        let rawJson = data.candidates[0].content.parts[0].text.trim();
        rawJson = rawJson.replace(/^```json/i, '').replace(/^```/, '').replace(/```$/, '').trim();
        
        const events = JSON.parse(rawJson);
        return res.status(200).json(events);

    } catch (error) {
        console.error("Server execution error:", error);
        return res.status(500).json({ error: 'Failed to process request on backend' });
    }
}
