<?php

namespace Tests\Feature;

use App\Filament\Resources\BaseResource;
use PHPUnit\Framework\TestCase;

/**
 * Filament allows by default, so every resource in every panel extends
 * BaseResource (which denies) and declares its own canAccess().
 */
class ResourceAccessFailsClosedTest extends TestCase
{
    public function test_a_resource_that_declares_nothing_denies(): void
    {
        $resource = new class extends BaseResource {};

        $this->assertFalse($resource::canAccess(),
            'A resource with no canAccess() of its own must not be reachable.');
    }

    /**
     * Every resource in every panel, by class name.
     *
     * @return array<string, string>
     */
    private function resources(): array
    {
        $root = dirname(__DIR__, 2).'/app/Filament';
        $found = [];

        $files = new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($root, \FilesystemIterator::SKIP_DOTS));

        foreach ($files as $file) {
            $relative = substr($file->getPathname(), strlen($root) + 1);

            // A resource's own pages and concerns live in a folder named after it.
            if (! preg_match('#(^|/)Resources/(\w+/)*\w+Resource\.php$#', $relative)
                || preg_match('#Resource/#', $relative)
                || basename($relative) === 'BaseResource.php') {
                continue;
            }

            $found['App\\Filament\\'.str_replace(['/', '.php'], ['\\', ''], $relative)] = $file->getPathname();
        }

        ksort($found);

        return $found;
    }

    public function test_every_resource_in_every_panel_is_found(): void
    {
        // Guards the scan itself: an empty list would pass everything below.
        $this->assertNotEmpty($this->resources());
    }

    public function test_every_resource_in_the_panel_extends_the_base(): void
    {
        $strays = [];

        foreach ($this->resources() as $name => $path) {
            $source = file_get_contents($path);

            if (! preg_match('/\bclass \w+ extends BaseResource\b/', $source)) {
                $strays[] = $name;
            }
        }

        $this->assertSame([], $strays,
            'These extend Filament\'s Resource directly, so they inherit allow: '
            .implode(', ', $strays));
    }

    public function test_every_resource_still_states_its_own_rule(): void
    {
        $silent = [];

        foreach (array_keys($this->resources()) as $class) {
            $name = $class;

            // Asked of the resolved method, not of the file's text: a rule
            // supplied by a trait is still the resource's own rule, and a
            // resource large enough to split its authorization into one is
            // exactly the sort that should not be failed for doing so.
            $declaring = (new \ReflectionMethod($class, 'canAccess'))->getDeclaringClass()->getName();

            if ($declaring === BaseResource::class) {
                $silent[] = $name;
            }
        }

        // Not strictly required (the base denies) but a resource nobody can
        // reach is almost never what was meant, so this catches the oversight
        // at the point it is made.
        $this->assertSame([], $silent,
            'These would be invisible to everyone: '.implode(', ', $silent));
    }
}
