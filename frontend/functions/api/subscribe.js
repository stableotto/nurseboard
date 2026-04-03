export async function onRequestPost(context) {
  const { request, env } = context;

  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
  };

  try {
    const body = await request.json();
    const { email, role, metro, state, employer } = body;

    if (!email || !email.includes("@")) {
      return new Response(JSON.stringify({ error: "Valid email required" }), {
        status: 400,
        headers: corsHeaders,
      });
    }

    // Read existing subscribers from KV
    const raw = await env.SUBSCRIBERS.get("list");
    const subscribers = raw ? JSON.parse(raw) : [];

    // Check for duplicate
    if (subscribers.some((s) => s.email === email.toLowerCase())) {
      return new Response(JSON.stringify({ ok: true, message: "Already subscribed" }), {
        headers: corsHeaders,
      });
    }

    // Add subscriber
    subscribers.push({
      email: email.toLowerCase().trim(),
      role: role || null,
      metro: metro || null,
      state: state || null,
      employer: employer || null,
      created_at: new Date().toISOString(),
    });

    await env.SUBSCRIBERS.put("list", JSON.stringify(subscribers));

    return new Response(JSON.stringify({ ok: true, message: "Subscribed" }), {
      headers: corsHeaders,
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: "Server error" }), {
      status: 500,
      headers: corsHeaders,
    });
  }
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
