export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { promptText, currentDate, timeZone } = req.body;
    const apiKey = process.env.GEMINI_API_KEY;

    if (!apiKey) {
        return res.status(500).json({ error: 'API key not found in Vercel environment' });
    }

    try {
        const systemInstruction = `
            You are a scheduling assistant. The user will provide a text describing events.
            - Current local date and time: "${currentDate}"
            - User's time zone: "${timeZone || 'UTC'}"

            Rules:
            1. Extract the event details from the user's input.
            2. Compute event start and end timestamps in the user's LOCAL time.
            3. Return strictly a valid JSON array of objects.
            4. Format "start" and "end" as "YYYY-MM-DDTHH:mm:ss" (NO trailing "Z" and NO UTC offsets).
            5. Default event duration to 30 minutes if unspecified.
            6. Do not wrap output in markdown codeblocks.

            JSON Schema:
            [
              {
                "title": "string",
                "start": "YYYY-MM-DDTHH:mm:ss",
                "end": "YYYY-MM-DDTHH:mm:ss"
              }
            ]
        `;

        const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: `${systemInstruction}\n\nUser Input: ${promptText}` }] }]
            })
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("Gemini API Error:", data);
            return res.status(500).json({ error: data.error?.message || 'Gemini API rejected the request.' });
        }

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
