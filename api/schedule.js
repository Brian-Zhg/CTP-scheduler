export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { promptText, currentDate } = req.body;
    
    // Securely pull the key from Vercel's environment variables
    const apiKey = process.env.GEMINI_API_KEY;

    if (!apiKey) {
        return res.status(500).json({ error: 'API key not found in Vercel' });
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

        const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: `${systemInstruction}\n\nUser Input: ${promptText}` }] }]
            })
        });

        const data = await response.json();
        
        // Clean up Markdown formatting from Gemini's response
        let rawJson = data.candidates[0].content.parts[0].text.trim();
        rawJson = rawJson.replace(/^```json/i, '').replace(/^```/, '').replace(/```$/, '').trim();
        
        const events = JSON.parse(rawJson);
        
        // Send the parsed JSON array back to your HTML frontend
        return res.status(200).json(events);

    } catch (error) {
        console.error(error);
        return res.status(500).json({ error: 'Failed to process request' });
    }
}
