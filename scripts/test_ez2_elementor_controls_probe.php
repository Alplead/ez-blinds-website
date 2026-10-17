<?php
/** Offline regression: Elementor stores Style-tab controls in a separate stack. */
namespace Elementor {
    class Plugin {
        public $elements_manager;
        public static function instance() {
            $plugin = new self();
            $plugin->elements_manager = new class {
                public function get_element_types($type) {
                    if ($type !== 'container') {
                        return null;
                    }
                    return new class {
                        public function get_controls($id = null) {
                            $base = array_fill_keys([
                                'background_background', 'background_slideshow_gallery',
                                'background_slideshow_slide_duration', 'background_slideshow_slide_transition',
                                'background_slideshow_transition_duration', 'background_slideshow_ken_burns',
                                'background_slideshow_ken_burns_zoom_direction',
                            ], ['type' => 'mock']);
                            $style = [
                                'background_overlay_background' => ['type' => 'mock'],
                                'background_overlay_opacity' => ['type' => 'mock'],
                            ];
                            if (getenv('EZ2_MOCK_MISSING_OVERLAY') === '1') {
                                unset($style['background_overlay_opacity']);
                            }
                            return $id === null ? $base : ($base[$id] ?? $style[$id] ?? null);
                        }
                    };
                }
            };
            return $plugin;
        }
    }
}
namespace {
    define('WP_CLI', true);
    define('ELEMENTOR_VERSION', '4.3.5');
    function get_option($key) {
        return [
            'home' => 'http://ez2-review.local',
            'siteurl' => 'http://ez2-review.local',
            'ez2_site_identity' => 'ez2-isolated-only',
        ][$key] ?? null;
    }
    function is_multisite() { return false; }
    function did_action($name) { return $name === 'elementor/loaded' ? 1 : 0; }

    if (getenv('EZ2_PROBE_CHILD') === '1') {
        require __DIR__ . '/ez2_elementor_controls_probe.php';
        exit;
    }

    putenv('EZ2_PROBE_CHILD=1');
    putenv('EZ2_EXPECTED_HOST=ez2-review.local');
    putenv('EZ2_EXPECTED_ELEMENTOR_VERSION=4.3.5');
    $cases = 0;
    foreach (['0', '1'] as $missing) {
        putenv('EZ2_MOCK_MISSING_OVERLAY=' . $missing);
        $process = proc_open([PHP_BINARY, __FILE__], [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        if (!is_resource($process)) {
            throw new \RuntimeException('Cannot launch isolated probe regression');
        }
        $stdout = stream_get_contents($pipes[1]);
        $stderr = stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        $status = proc_close($process);
        if ($missing === '0') {
            if ($status !== 0 || strpos($stdout, 'EZ2_ELEMENTOR_CONTROLS_PASS') === false) {
                throw new \RuntimeException('Split Style-tab controls were rejected: ' . $stderr);
            }
        } elseif ($status === 0 || strpos($stderr, 'EZ2_ELEMENTOR_MISSING_CONTROLS: background_overlay_opacity') === false) {
            throw new \RuntimeException('Missing overlay control was accepted: ' . $stdout . $stderr);
        }
        ++$cases;
    }
    echo "EZ2_ELEMENTOR_CONTROLS_PROBE_REGRESSION_PASS cases=$cases\n";
}
