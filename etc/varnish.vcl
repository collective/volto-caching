vcl 4.0;

import std;
import directors;

/* Configure zope clients as backends */

backend client_01_8080 {
  .host = "backend";
  .port = "8080";
  .connect_timeout = 0.4s;
  .first_byte_timeout = 300s;
  .between_bytes_timeout = 60s;
  .probe = {
    .url = "/ok";
    .timeout = 5s;
    .interval = 15s;
    .window = 10;
    .threshold = 8;
  }
}


/* Only allow PURGE from localhost and API-Server */
acl purge_allowed {
  "localhost";
  "backend";
  "127.0.0.1";
  "172.16.0.0/12";
  "192.168.0.0/16";
}

sub vcl_init {
  # Use round_robin director type
  new cluster = directors.round_robin();
  cluster.add_backend(client_01_8080);
}

sub vcl_recv {
  # Send requests to the cluster using a round robin director
  set req.backend_hint = cluster.backend();

  # Sanitize compression handling
  if (req.http.Accept-Encoding) {
    if (req.url ~ "\.(jpg|png|gif|gz|tgz|bz2|tbz|mp3|ogg)$") {
        # No point in compressing these
        unset req.http.Accept-Encoding;
    } elsif (req.http.Accept-Encoding ~ "gzip") {
        set req.http.Accept-Encoding = "gzip";
    } elsif (req.http.Accept-Encoding ~ "deflate" && req.http.user-agent !~ "MSIE") {
        set req.http.Accept-Encoding = "deflate";
    } else {
        # unknown algorithm
        unset req.http.Accept-Encoding;
    }
  }

  # Sanitize cookies so they do not needlessly destroy cacheability for anonymous pages
  if (req.http.Cookie) {
    set req.http.Cookie = ";" + req.http.Cookie;
    set req.http.Cookie = regsuball(req.http.Cookie, "; +", ";");
    set req.http.Cookie = regsuball(req.http.Cookie, ";(sticky|I18N_LANGUAGE|statusmessages|__ac|_ZopeId|__cp|beaker\.session|authomatic|serverid|__rf)=", "; \1=");
    set req.http.Cookie = regsuball(req.http.Cookie, ";[^ ][^;]*", "");
    set req.http.Cookie = regsuball(req.http.Cookie, "^[; ]+|[; ]+$", "");

    if (req.http.Cookie == "") {
        unset req.http.Cookie;
    }
  }

  # POST, Logins and edits
  if (req.method == "POST" || req.method == "PATCH" || req.method == "DELETE") {
      return(pass);
  } elsif (req.method == "PURGE" || req.method == "BAN") {
    if (client.ip !~ purge_allowed) {
        return (synth(403, req.method + " not allowed from " + client.ip + ". Access denied."));
    }
    if (!req.http.x-invalidate-pattern) {
        # Purge
        return (purge);
    }
    if (std.ban(req.http.x-invalidate-pattern)) {
        return (synth(200, "BAN added " + req.http.x-invalidate-pattern));
    } else {
        return (synth(400, std.ban_error()));
    }
  }

  /* If user is validated, PASS, unconditionally */
  if (req.http.Authorization) {
    return(pass);
  }

  return(hash);

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
  if (req.http.Authorization) {
    set resp.http.X-Auth = "Logged-in";
  } else {
    set resp.http.X-Auth = "Anon";
  }
}
