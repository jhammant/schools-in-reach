// CloudFront viewer-request function: send the bare domain to www, keeping the path and query.
function handler(event) {
  var req = event.request;
  var qs = [];
  for (var k in req.querystring) {
    var v = req.querystring[k];
    qs.push(v.multiValue ? v.multiValue.map(function (m) { return k + "=" + m.value; }).join("&") : k + "=" + v.value);
  }
  var location = "https://www.schoolsinreach.com" + req.uri + (qs.length ? "?" + qs.join("&") : "");
  return { statusCode: 301, statusDescription: "Moved Permanently", headers: { location: { value: location }, "cache-control": { value: "public, max-age=3600" } } };
}
