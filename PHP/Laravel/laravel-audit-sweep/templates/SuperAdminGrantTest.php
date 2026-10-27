<?php

namespace Tests\Feature;

use App\Models\User;
use Database\Seeders\RolesSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SuperAdminGrantTest extends TestCase
{
    use RefreshDatabase;

    public function test_the_configured_account_is_made_super_admin(): void
    {
        $owner = User::factory()->create(['email' => 'owner@example.invalid.k3v9q']);
        config(['app.super_admin_email' => $owner->email]);

        $this->seed(RolesSeeder::class);

        $this->assertTrue($owner->fresh()->hasRole('super_admin'));
    }

    public function test_nobody_is_made_super_admin_when_none_is_configured(): void
    {
        User::factory()->create(['email' => 'owner@example.invalid.k3v9q']);
        config(['app.super_admin_email' => null]);

        $this->seed(RolesSeeder::class);

        $this->assertSame(0, User::role('super_admin')->count());
    }
}
