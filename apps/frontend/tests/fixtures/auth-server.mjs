/** Loopback-only Auth fixture. Contains no real users, credentials or data. */
import http from "node:http";

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "fixture@example.test",
  aud: "authenticated",
  role: "authenticated",
  app_metadata: {},
  user_metadata: {},
};

http.createServer((request, response) => {
  response.setHeader("Content-Type", "application/json");
  if (request.url === "/health") {
    response.end(JSON.stringify({ status: "ok" }));
  } else if (request.url === "/auth/v1/user" && request.headers.authorization?.endsWith(".fixture")) {
    response.end(JSON.stringify(user));
  } else {
    response.statusCode = 401;
    response.end(JSON.stringify({ message: "Fixture token required" }));
  }
}).listen(3041, "127.0.0.1");
