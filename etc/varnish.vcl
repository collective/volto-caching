vcl 4.0;

import std;
import directors;

backend traefik_loadbalancer {
    .host = "webserver";
    .port = "80";
    .connect_timeout = 2s;
    .first_byte_timeout = 300s;
    .between_bytes_timeout  = 60s;
}

/* Only allow PURGE from localhost and API-Server */
acl purge {
  "localhost";
  "backend";
  "127.0.0.1";
  "172.16.0.0/12";
  "10.0.0.0/8";
  "192.168.0.0/16";
}

sub vcl_init {
  new cluster_loadbalancer = directors.round_robin();
  cluster_loadbalancer.add_backend(traefik_loadbalancer);
}

sub vcl_recv {
  set req.backend_hint = cluster_loadbalancer.backend();
  set req.http.X-Varnish-Routed = "1";
  set req.http.X-Varnish-ReqType = "Default";

  # Sanitize cookies so they do not needlessly destroy cacheability for anonymous pages
  if (req.http.Cookie) {
    set req.http.Cookie = ";" + req.http.Cookie;
    set req.http.Cookie = regsuball(req.http.Cookie, "; +", ";");
    set req.http.Cookie = regsuball(req.http.Cookie, ";(sticky|I18N_LANGUAGE|statusmessages|__ac|_ZopeId|__cp|beaker\.session|authomatic|serverid|__rf|auth_token)=", "; \1=");
    set req.http.Cookie = regsuball(req.http.Cookie, ";[^ ][^;]*", "");
    set req.http.Cookie = regsuball(req.http.Cookie, "^[; ]+|[; ]+$", "");

    if (req.http.Cookie == "") {
        unset req.http.Cookie;
    }
  }

  if (
      (req.http.Cookie && (req.http.Cookie ~ "__ac(_(name|password|persistent))?=" || req.http.Cookie ~ "_ZopeId" || req.http.Cookie ~ "auth_token")) ||
      (req.http.Authenticate) ||
      (req.http.Authorization)
  ) {
    set req.http.X-Varnish-ReqType = "Auth";
    return(pass);
  }

  set req.http.Cookied = "0";

  if (req.method == "PURGE") {
      if (!client.ip ~ purge) {
          return (synth(405, "Not allowed."));
      } else {
          ban("req.url == " + req.url);
          return (synth(200, "Purged."));
      }

  } elseif (req.method == "BAN") {
      # Same ACL check as above:
      if (!client.ip ~ purge) {
          return (synth(405, "Not allowed."));
      }
      ban("req.http.host == " + req.http.host + "&& req.url == " + req.url);
      # Throw a synthetic page so the
      # request won't go to the backend.
      return (synth(200, "Ban added"));

  } elseif (req.method != "GET" &&
      req.method != "HEAD" &&
      req.method != "PUT" &&
      req.method != "POST" &&
      req.method != "PATCH" &&
      req.method != "TRACE" &&
      req.method != "OPTIONS" &&
      req.method != "DELETE") {
      /* Non-RFC2616 or CONNECT which is weird. */
      return (pipe);
  } elseif (req.method != "GET" &&
      req.method != "HEAD" &&
      req.method != "OPTIONS") {
      /* POST, PUT, PATCH will pass, always */
      return(pass);
  }

  if (req.url ~ "\/@@(images|download|)\/?(.*)?$"){
    set req.http.X-Varnish-ReqType = "Blob";
    return(hash);
  } elseif (req.url ~ "\/\+\+api\+\+/?(.*)?$") {
    set req.http.X-Varnish-ReqType = "api";
    return(hash);
  } else {
    set req.http.X-Varnish-ReqType = "Express";
    return(hash);
  }

}

sub vcl_pipe {
  /* This is not necessary if you do not do any request rewriting. */
  set req.http.connection = "close";
}

sub vcl_purge {
  return (synth(200, "PURGE: " + req.url + " - " + req.hash));
}

sub vcl_hit {
  if (obj.ttl >= 0s) {
    // A pure unadulterated hit, deliver it
    return (deliver);
  } elsif (obj.ttl + obj.grace > 0s) {
    // Object is in grace, deliver it
    // Automatically triggers a background fetch
    return (deliver);
  } else {
    return (restart);
  }
}

sub vcl_backend_response {

  set beresp.http.X-Varnish-ReqType = bereq.http.X-Varnish-ReqType;

  # Don't allow static files to set cookies.
  # (?i) denotes case insensitive in PCRE (perl compatible regular expressions).
  # make sure you edit both and keep them equal.
  if (bereq.url ~ "(?i)\.(pdf|asc|dat|txt|doc|xls|ppt|tgz|png|gif|jpeg|jpg|ico|swf|css|js)(\?.*)?$") {
    unset beresp.http.set-cookie;
  }
  if (beresp.http.Set-Cookie) {
    set beresp.http.X-Varnish-Action = "FETCH (pass - response sets cookie)";
    set beresp.uncacheable = true;
    set beresp.ttl = 120s;
    return(deliver);
  }
  if (beresp.http.Cache-Control ~ "(private|no-cache|no-store)") {
    set beresp.http.X-Varnish-Action = "FETCH (pass - cache control disallows)";
    set beresp.uncacheable = true;
    set beresp.ttl = 120s;
    return(deliver);
  }

  # if (beresp.http.Authorization && !beresp.http.Cache-Control ~ "public") {
  # Do NOT cache if there is an "Authorization" header
  # beresp never has an Authorization header in beresp, right?
  if (beresp.http.Authorization) {
    set beresp.http.X-Varnish-Action = "FETCH (pass - authorized and no public cache control)";
    set beresp.uncacheable = true;
    set beresp.ttl = 120s;
    return(deliver);
  }

  # Use this rule IF no cache-control
  if ((beresp.http.X-Varnish-ReqType ~ "Express") && (!beresp.http.Cache-Control)) {
    set beresp.http.X-Varnish-Action = "INSERT (10s caching)";
    set beresp.uncacheable = false;
    set beresp.ttl = 10s;
    set beresp.grace = 20s;
    return(deliver);
  }

  if (!beresp.http.Cache-Control) {
    set beresp.http.X-Varnish-Action = "FETCH (override - backend not setting cache control)";
    set beresp.uncacheable = true;
    set beresp.ttl = 120s;
    return (deliver);
  }

  if (beresp.http.X-Anonymous && !beresp.http.Cache-Control) {
    set beresp.http.X-Varnish-Action = "FETCH (override - anonymous backend not setting cache control)";
    set beresp.ttl = 600s;
    return (deliver);
  }

  set beresp.http.X-Varnish-Action = "FETCH (insert)";
  if (bereq.http.x-vcl-debug) {
    set beresp.http.x-varnish-uncacheable = beresp.uncacheable;
    set beresp.http.x-varnish-ttl = beresp.ttl;
    set beresp.http.x-varnish-grace = beresp.grace;
  }

  return (deliver);
}

sub vcl_deliver {

  set resp.http.X-Powered-By = "Plone (https://plone.org)";

  if (obj.hits > 0) {
    set resp.http.X-Cache = "HIT";
  } else {
    set resp.http.X-Cache = "MISS";
  }

  set resp.http.X-Hits = obj.hits;
  set resp.http.X-TTL = obj.ttl;
  set resp.http.X-Grace = obj.grace;

  # User is validated
  if (
      (req.http.Cookie && (req.http.Cookie ~ "__ac(_(name|password|persistent))?=" || req.http.Cookie ~ "_ZopeId" || req.http.Cookie ~ "auth_token")) ||
      (req.http.Authenticate) ||
      (req.http.Authorization)
  ) {
    set resp.http.X-Auth = "Logged-in";
  } else {
    set resp.http.X-Auth = "Anon";
  }
}
