<?php
/**
 * Experimental, PRIVATE ONLY portfolio board for Owner art-direction review.
 * All actual photograph bytes remain in the authenticated WordPress media
 * library. No person, address or installation claim is inferred from filenames.
 */
add_action('template_redirect', function () {
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
    if ($path !== '/ez2-photo-gallery/' && $path !== '/ez2-photo-gallery') return;
    $home = wp_parse_url(home_url(), PHP_URL_HOST);
    if (!is_string($home) || !preg_match('/^sb-[a-z0-9]+\.vercel\.run$/', $home)) {
        status_header(403);
        exit;
    }
    $all = get_posts(['post_type'=>'attachment','post_status'=>'inherit','posts_per_page'=>100,'orderby'=>'ID','order'=>'ASC']);
    $collections = [
        'Roller Blinds' => [],
        'Plantation Shutters' => [],
        'Retractable Flyscreens' => [],
        'Sheer Curtains / Multi-product' => [],
    ];
    foreach ($all as $attachment) {
        if (get_post_mime_type($attachment) !== 'image/webp') continue;
        $basename = strtolower(basename((string)get_attached_file($attachment->ID)));
        $category = null;
        if (str_contains($basename,'roller') || str_contains($basename,'imag3884')) $category='Roller Blinds';
        elseif (str_contains($basename,'plantation') || str_contains($basename,'img_4689')) $category='Plantation Shutters';
        elseif (str_contains($basename,'retractable') || str_contains($basename,'rfs') || preg_match('/imag(355|4409|4430|4641)/',$basename)) $category='Retractable Flyscreens';
        elseif (str_contains($basename,'pxl_')) $category='Sheer Curtains / Multi-product';
        if ($category) {
            $collections[$category][] = [
                'url'=>(string)wp_get_attachment_url($attachment->ID),
                'alt'=> (string)(get_post_meta($attachment->ID,'_wp_attachment_image_alt',true) ?: $category . ' — real EZ installation photograph'),
            ];
        }
    }
    $photos = array_sum(array_map('count', $collections));
    status_header(200);
    header('Cache-Control: private, no-store');
    header('X-Robots-Tag: noindex, nofollow, noarchive');
    ?><!doctype html><html lang="en-AU"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex,nofollow,noarchive">
    <title>Real EZ Installations — Private Art Direction Review</title>
    <style>
    :root{--green:#213c34;--paper:#f7f4ef;--ink:#1b2d28;--line:#d8d7cd}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{background:var(--paper);color:var(--ink);font-family:Arial,Helvetica,sans-serif;margin:0;line-height:1.5}
    a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
    .nav{display:flex;justify-content:space-between;align-items:center;padding:18px max(4vw,22px);background:var(--green);color:#fff;gap:20px;flex-wrap:wrap}
    .brand{font-size:14px;font-weight:700;letter-spacing:.16em}.links{display:flex;gap:24px;font-size:13px}.eyebrow{font-size:11px;font-weight:700;letter-spacing:.22em;text-transform:uppercase}
    .hero{height:min(82vh,820px);min-height:470px;background:#3d4b41;position:relative;overflow:hidden;color:#fff;display:flex;align-items:end}
    .hero img{height:100%;width:100%;object-fit:cover;position:absolute;inset:0;animation:slowzoom 26s linear infinite alternate}
    .hero:after{content:"";position:absolute;inset:0;background:linear-gradient(0deg,rgba(11,31,24,.75),transparent 70%)}
    .hero .copy{position:relative;z-index:1;padding:6vw 6vw 5vw;max-width:950px}.hero h1{font-family:Georgia,serif;font-size:clamp(38px,6vw,82px);font-weight:400;line-height:1.05;margin:12px 0 16px;letter-spacing:-.035em}
    .hero p{max-width:570px;font-size:clamp(15px,1.6vw,20px);font-weight:400}.hero .eyebrow{color:#efe3cd}
    section{padding:72px max(4vw,22px);max-width:1700px;margin:auto;border-bottom:1px solid var(--line)}.intro{max-width:950px}.intro h2,.sectionhead h2{font-family:Georgia,serif;font-weight:400;letter-spacing:-.035em;font-size:clamp(32px,4.5vw,64px);line-height:1.1;margin:.2em 0}
    .sectionhead{display:flex;gap:30px;align-items:end;justify-content:space-between;margin-bottom:26px;flex-wrap:wrap}
    .count{font-size:13px;opacity:.65}.mosaic{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:clamp(10px,1.5vw,24px)}
    figure{margin:0;grid-column:span 4;position:relative;overflow:hidden;background:#e1e1dc;min-height:220px}figure:nth-child(5n+1),figure:nth-child(5n+4){grid-column:span 6}
    figure img{width:100%;height:100%;aspect-ratio:4/3;object-fit:cover;display:block;transition:transform .7s}figure:hover img{transform:scale(1.035)}
    figure figcaption{position:absolute;bottom:0;left:0;right:0;padding:26px 18px 13px;background:linear-gradient(transparent,rgba(0,0,0,.5));color:#fff;font-size:12px}
    .note{background:var(--green);color:#fff;padding:35px 5vw;font-size:14px}.note p{max-width:900px;margin:0 auto} 
    @keyframes slowzoom{from{transform:scale(1)}to{transform:scale(1.08)}}@media(max-width:800px){section{padding:46px 5vw}figure{grid-column:span 6!important;min-height:150px}.hero{height:70vh;min-height:460px}}@media(max-width:480px){figure{grid-column:span 12!important}.nav{padding:15px 5vw}.links{gap:14px;font-size:12px}.hero .copy{padding:8vw}.hero h1{font-size:44px}}
    @media(prefers-reduced-motion:reduce){.hero img{animation:none}figure img{transition:none}}
    </style></head><body>
    <header class="nav"><div class="brand">EZ BLINDS &amp; SHUTTERS</div><div class="links"><a href="/">Website Home</a><a href="/ez2-elementor-hero-lab/">Elementor Hero</a></div></header>
    <?php
    $hero = $collections['Sheer Curtains / Multi-product'][0]['url'] ?? ($collections['Roller Blinds'][0]['url'] ?? '');
    ?>
    <div class="hero"><?php if ($hero):?><img src="<?php echo esc_url($hero);?>" alt="Original EZ installation photograph" fetchpriority="high"><?php endif;?>
      <div class="copy"><div class="eyebrow">EZ2 / Private Design Study / Real Projects</div>
      <h1>Designed for real spaces.<br>Beautifully finished.</h1>
      <p>Original EZ Blinds &amp; Shutters installation photography. A photo-first direction for the new website.</p></div>
    </div>
    <section class="intro"><div class="eyebrow">The Photography Library</div>
    <h2><?php echo (int)$photos;?> real project photographs.<br>No stock-image placeholders.</h2>
    <p>This protected gallery groups the website-ready photographs already selected from the Owner's Drive library. Composition and photo selection are for review, not public publication approval.</p></section>
    <?php foreach($collections as $category=>$items): if(!$items)continue;?>
    <section><div class="sectionhead"><div><div class="eyebrow">Authentic Installations</div><h2><?php echo esc_html($category);?></h2></div><span class="count"><?php echo count($items);?> photographs</span></div>
    <div class="mosaic">
    <?php foreach($items as $i=>$item):?><figure><img loading="lazy" decoding="async" src="<?php echo esc_url($item['url']);?>" alt="<?php echo esc_attr($item['alt']);?>"><figcaption><?php echo esc_html($category);?> &nbsp; / &nbsp; <?php echo sprintf('%02d',$i+1);?></figcaption></figure><?php endforeach;?>
    </div></section>
    <?php endforeach;?>
    <aside class="note"><p><strong>Private preview only.</strong> Product details, customer identity, image crop and public publication permission are not yet approved. Images are sourced from the Owner-supplied Drive master WebP bundle; no customer records were copied.</p></aside>
    </body></html><?php exit;
}, -1);
